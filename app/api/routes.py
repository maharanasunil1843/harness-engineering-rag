"""FastAPI route handlers."""
import asyncio
import json
import logging
import os

import psycopg
from fastapi import APIRouter, HTTPException, Request
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
from app.retrieval.cache import cache_stats
from app.retrieval.rate_limiter import check_rate_limit

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


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


# ── POST /api/query ───────────────────────────────────────────────────────────

@router.post("/query", response_model=QueryResponse)
async def query(request: Request, body: QueryRequest) -> QueryResponse:
    rate = await check_rate_limit(getattr(request.state, "user_id", "default"))
    if not rate.allowed:
        raise HTTPException(
            status_code=429,
            detail={"message": "Rate limit exceeded", "reset_in": rate.reset_in},
            headers={"Retry-After": str(int(rate.reset_in))},
        )

    try:
        answer = await ask(body.query)
    except Exception as exc:
        logger.exception("ask() failed")
        raise HTTPException(status_code=500, detail={"message": str(exc)}) from exc

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
    rate = await check_rate_limit(getattr(request.state, "user_id", "default"))
    if not rate.allowed:
        raise HTTPException(
            status_code=429,
            detail={"message": "Rate limit exceeded", "reset_in": rate.reset_in},
            headers={"Retry-After": str(int(rate.reset_in))},
        )

    async def event_generator():
        try:
            # Status: classifying
            yield {"event": "status", "data": json.dumps({"step": "classifying"})}
            await asyncio.sleep(0)

            # Run the full pipeline — supervisor handles all routing internally.
            # True per-hop streaming requires wiring each graph node to yield events;
            # that is a production upgrade. For now we emit lifecycle status events
            # around the single pipeline call and stream tokens from the final answer.
            from app.agents.query_rewriter import rewrite_and_classify
            classified = await rewrite_and_classify(body.query)
            intent = classified.intent

            # Status: routing based on intent
            if intent == "sql":
                yield {"event": "status", "data": json.dumps({"step": "querying_sql"})}
            elif intent in ("retrieval", "hybrid"):
                yield {
                    "event": "status",
                    "data": json.dumps({"step": "retrieving", "intent": intent}),
                }
            await asyncio.sleep(0)

            # Run retrieval to surface sources early if applicable
            sources_emitted: list[SourceInfo] = []
            if intent in ("retrieval", "hybrid"):
                from app.retrieval.hybrid import hybrid_retrieve, _embed_query
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
                    yield {"event": "source", "data": src.model_dump_json()}
                    await asyncio.sleep(0)

            # Status: synthesizing
            yield {"event": "status", "data": json.dumps({"step": "synthesizing"})}
            await asyncio.sleep(0)

            # Full pipeline call for final answer (uses cached embedding above where possible)
            answer = await ask(body.query)

            # Stream tokens: split answer into ~20-word chunks with 50ms delay.
            # Production upgrade: use Anthropic streaming API (client.messages.stream())
            # and forward each text_delta event directly as a "token" SSE event.
            words = answer.answer.split()
            chunk_size = 20
            for i in range(0, len(words), chunk_size):
                chunk_text = " ".join(words[i : i + chunk_size])
                if i + chunk_size < len(words):
                    chunk_text += " "
                yield {"event": "token", "data": json.dumps({"text": chunk_text})}
                await asyncio.sleep(0.05)

            # Done event with full response payload
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
            logger.exception("Streaming query failed")
            yield {"event": "error", "data": json.dumps({"message": str(exc)})}

    return EventSourceResponse(event_generator())


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

    return HealthResponse(
        status="healthy" if db_ok and cache_ok else "degraded",
        db_connected=db_ok,
        cache_connected=cache_ok,
        cache_stats=stats,
    )


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
