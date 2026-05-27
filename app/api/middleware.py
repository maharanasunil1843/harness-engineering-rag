"""CORS, request logging, and rate-limit middleware."""
import logging
import time

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
]

# Wildcard pattern for Vercel preview deployments — handled manually below
# because CORSMiddleware doesn't support glob patterns in allow_origins.
_VERCEL_SUFFIX = ".vercel.app"


def _origin_allowed(origin: str) -> bool:
    if origin in _CORS_ORIGINS:
        return True
    if origin.endswith(_VERCEL_SUFFIX):
        return True
    return False


def setup_middleware(app: FastAPI) -> None:
    # ── CORS ─────────────────────────────────────────────────────────────────
    # allow_origins=["*"] would be simplest but blocks credentialed requests.
    # We use a custom allow_origin_regex that covers localhost + *.vercel.app.
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?|https://.*\.vercel\.app",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Request logging + rate-limit gate ────────────────────────────────────
    @app.middleware("http")
    async def logging_and_rate_limit(request: Request, call_next) -> Response:
        t0 = time.perf_counter()

        # Rate-limit guard on query endpoints only
        if request.url.path.startswith("/api/query"):
            from app.retrieval.rate_limiter import check_rate_limit
            try:
                result = await check_rate_limit()
                if not result.allowed:
                    return JSONResponse(
                        status_code=429,
                        content={"message": "Rate limit exceeded", "reset_in": result.reset_in},
                        headers={"Retry-After": str(int(result.reset_in))},
                    )
            except Exception:
                pass  # Rate limiter failure is non-fatal — let request through

        response = await call_next(request)
        latency_ms = (time.perf_counter() - t0) * 1000

        logger.info(
            "%s %s → %d (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            latency_ms,
        )
        response.headers["X-Latency-Ms"] = f"{latency_ms:.1f}"
        return response
