"""FastAPI route handlers."""
import asyncio
import json
import logging
import os
import time

import psycopg
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse
from upstash_redis import Redis

from app.agents.supervisor import ask
from app.api.schemas import (
    HealthResponse,
    QueryRequest,
    QueryResponse,
    SourceInfo,
)
from app.config import get_settings
from app.observability.metrics import get_metrics_snapshot, record_query
from app.observability.tracing import is_tracing_healthy
from app.retrieval.cache import cache_stats
from app.retrieval.rate_limiter import check_rate_limit

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

# Hard cap on streaming connection lifetime. Past this, the generator yields
# an error event and closes — without this a stuck downstream call would hang
# the client browser forever.
_STREAM_TIMEOUT_S = 120.0


# ── Helpers ──────────────────────────────────────────────────────────────────

def _sources_from_answer(answer) -> list[SourceInfo]:
    return [
        SourceInfo(
            chunk_id=s.get("chunk_id"),
            doc_id=s.get("doc_id"),
            doc_title=s.get("doc_title"),
            element_type=s.get("element_type"),
            score=s.get("score"),
            source_type=s.get("source_type", "retrieval"),
        )
        for s in (answer.sources or [])
    ]


def _rate_limit_key(request: Request) -> str:
    """Per-user (Clerk) or per-IP rate-limit key.

    Clerk forwards the authenticated user id via `x-clerk-user-id`. If absent
    (unauthenticated traffic in dev) we fall back to the client IP. The
    previous code used a hard-coded `default`, which meant every user shared
    one bucket — a single noisy client could DoS everyone.
    """
    clerk_uid = request.headers.get("x-clerk-user-id")
    if clerk_uid:
        return f"u:{clerk_uid}"
    # X-Forwarded-For is set by Vercel / any reverse proxy. Take the first hop.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return f"ip:{fwd.split(',')[0].strip()}"
    client = request.client
    return f"ip:{client.host if client else 'unknown'}"


# ── POST /api/query ───────────────────────────────────────────────────────────

@router.post("/query", response_model=QueryResponse)
async def query(request: Request, body: QueryRequest) -> QueryResponse:
    rate = await check_rate_limit(_rate_limit_key(request))
    if not rate.allowed:
        raise HTTPException(
            status_code=429,
            detail={"message": "Rate limit exceeded", "reset_in": rate.reset_in},
            headers={"Retry-After": str(int(rate.reset_in))},
        )

    t0 = time.perf_counter()
    error = False
    try:
        answer = await ask(body.query)
    except Exception as exc:
        error = True
        logger.exception("ask() failed")
        record_query(
            intent="error",
            latency_ms=(time.perf_counter() - t0) * 1000,
            cache_hit=False,
            tokens=0,
            cost=0.0,
            error=True,
        )
        raise HTTPException(status_code=500, detail={"message": str(exc)}) from exc
    finally:
        if not error:
            record_query(
                intent="unknown",  # supervisor doesn't surface intent on this path
                latency_ms=(time.perf_counter() - t0) * 1000,
                cache_hit=False,
                tokens=0,
                cost=0.0,
                error=False,
            )

    return QueryResponse(
        answer=answer.answer,
        sources=_sources_from_answer(answer),
        confidence=answer.confidence,
        trace_id=answer.trace_id,
        latency_ms=answer.latency_ms,
        cache_hit=False,
    )


# ── POST /api/query/stream ────────────────────────────────────────────────────

@router.post("/query/stream")
async def query_stream(request: Request, body: QueryRequest):
    rate = await check_rate_limit(_rate_limit_key(request))
    if not rate.allowed:
        raise HTTPException(
            status_code=429,
            detail={"message": "Rate limit exceeded", "reset_in": rate.reset_in},
            headers={"Retry-After": str(int(rate.reset_in))},
        )

    async def event_generator():
        t_start = time.perf_counter()
        intent = "unknown"
        error = False
        try:
            # Yield the first status event IMMEDIATELY — confirms connection
            # before any LLM call (must be < 500ms).
            yield {"event": "status", "data": json.dumps({"step": "classifying"})}
            await asyncio.sleep(0)

            async def _run_pipeline():
                from app.agents.query_rewriter import rewrite_and_classify
                from app.retrieval.hybrid import _embed_query, hybrid_retrieve

                classified = await rewrite_and_classify(body.query)
                local_intent = classified.intent

                events: list[dict] = []
                sources_emitted: list[SourceInfo] = []

                if local_intent == "sql":
                    events.append({"event": "status",
                                   "data": json.dumps({"step": "querying_sql"})})
                elif local_intent in ("retrieval", "hybrid"):
                    events.append({"event": "status",
                                   "data": json.dumps({"step": "retrieving",
                                                       "intent": local_intent})})

                if local_intent in ("retrieval", "hybrid"):
                    embedding = _embed_query(classified.rewritten)
                    chunks = await hybrid_retrieve(
                        classified.rewritten, top_k=10, query_embedding=embedding
                    )
                    for chunk in chunks:
                        src = SourceInfo(
                            chunk_id=chunk.chunk_id,
                            doc_id=chunk.doc_id,
                            doc_title=chunk.metadata.get("title", chunk.doc_id),
                            element_type=chunk.element_type,
                            score=chunk.score,
                            source_type="retrieval",
                        )
                        sources_emitted.append(src)
                        events.append({"event": "source",
                                       "data": src.model_dump_json()})

                events.append({"event": "status",
                               "data": json.dumps({"step": "synthesizing"})})

                answer = await ask(body.query)
                return local_intent, events, answer

            # Wall-clock cap for the whole pipeline call.
            try:
                intent, events, answer = await asyncio.wait_for(
                    _run_pipeline(), timeout=_STREAM_TIMEOUT_S
                )
            except asyncio.TimeoutError as exc:
                raise TimeoutError(
                    f"stream exceeded {_STREAM_TIMEOUT_S:.0f}s timeout"
                ) from exc

            for ev in events:
                yield ev
                await asyncio.sleep(0)

            # Stream tokens: split answer into ~20-word chunks with 50ms delay.
            words = answer.answer.split()
            chunk_size = 20
            for i in range(0, len(words), chunk_size):
                chunk_text = " ".join(words[i : i + chunk_size])
                if i + chunk_size < len(words):
                    chunk_text += " "
                yield {"event": "token", "data": json.dumps({"text": chunk_text})}
                await asyncio.sleep(0.05)

            response = QueryResponse(
                answer=answer.answer,
                sources=_sources_from_answer(answer),
                confidence=answer.confidence,
                trace_id=answer.trace_id,
                latency_ms=answer.latency_ms,
                cache_hit=False,
                intent=intent,
            )
            yield {"event": "done", "data": response.model_dump_json()}

        except Exception as exc:
            error = True
            logger.exception("Streaming query failed")
            # Always yield a user-friendly error event so the browser knows
            # to stop waiting. Never let an exception propagate silently.
            yield {
                "event": "error",
                "data": json.dumps({
                    "message": "The server encountered an error while processing your query. Please try again.",
                    "detail": str(exc)[:200],
                }),
            }
        finally:
            record_query(
                intent=intent,
                latency_ms=(time.perf_counter() - t_start) * 1000,
                cache_hit=False,
                tokens=0,
                cost=0.0,
                error=error,
            )

    # Prevent Nginx/proxies from buffering the SSE stream — without these
    # headers the browser sees nothing until the upstream finishes.
    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }
    return EventSourceResponse(event_generator(), headers=headers)


# ── GET /api/health ───────────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    s = get_settings()

    db_ok = False
    try:
        with psycopg.connect(os.environ.get("DATABASE_URL", s.database_url)) as conn:
            conn.execute("SELECT 1")
        db_ok = True
    except Exception:
        pass

    cache_ok = False
    stats: dict | None = None
    try:
        r = Redis(url=s.upstash_redis_rest_url, token=s.upstash_redis_rest_token)
        r.ping()
        cache_ok = True
        stats = await cache_stats()
    except Exception:
        pass

    metrics = get_metrics_snapshot()
    return HealthResponse(
        status="healthy" if db_ok and cache_ok else "degraded",
        db_connected=db_ok,
        cache_connected=cache_ok,
        cache_stats=stats,
        tracing_healthy=is_tracing_healthy(),
        query_count=metrics["query_count"],
        cache_hit_rate=metrics["cache_hit_rate"],
    )


# ── GET /api/metrics ──────────────────────────────────────────────────────────

@router.get("/metrics")
async def metrics_endpoint(x_admin_key: str | None = Header(default=None)) -> dict:
    """Internal observability — gated by ADMIN_KEY env var.

    If ADMIN_KEY is unset OR the supplied X-Admin-Key header doesn't match,
    return 403. This is NOT a user-facing endpoint.
    """
    s = get_settings()
    if not s.admin_key or x_admin_key != s.admin_key:
        raise HTTPException(status_code=403, detail="forbidden")
    return get_metrics_snapshot()


# ── GET /api/cache/stats ──────────────────────────────────────────────────────

@router.get("/cache/stats")
async def get_cache_stats() -> dict:
    try:
        return await cache_stats()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── DELETE /api/cache ─────────────────────────────────────────────────────────

@router.delete("/cache")
async def clear_cache() -> dict:
    try:
        s = get_settings()
        r = Redis(url=s.upstash_redis_rest_url, token=s.upstash_redis_rest_token)
        keys = r.smembers("cache:index")
        for k in keys:
            r.delete(k)
        r.delete("cache:index")
        r.delete("cache:hits")
        r.delete("cache:misses")
        return {"cleared": True, "entries_removed": len(keys)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── Validation-error → 400 (so prompt-injection / empty queries don't 422) ──

def install_validation_handler(app):
    """Convert pydantic 422s on QueryRequest into clean 400s with our message."""
    from fastapi.exceptions import RequestValidationError

    @app.exception_handler(RequestValidationError)
    async def _handler(request, exc):
        # Surface the first validator message — pydantic nests them in `ctx`.
        msg = "invalid request"
        for err in exc.errors():
            if err.get("loc", [None, None])[-1] == "query":
                msg = err.get("msg", msg)
                break
        return JSONResponse(status_code=400, content={"detail": msg})
