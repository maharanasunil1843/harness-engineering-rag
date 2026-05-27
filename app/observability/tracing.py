"""Per-hop LangSmith tracing wired into every agent node."""
import asyncio
import functools
import os
import time
from typing import Any

from langsmith import Client, RunTree

from app.config import get_settings

_client: Client | None = None


def _get_client() -> Client:
    global _client
    if _client is None:
        settings = get_settings()
        os.environ.setdefault("LANGSMITH_API_KEY", settings.langsmith_api_key)
        os.environ.setdefault("LANGSMITH_PROJECT", settings.langsmith_project)
        _client = Client()
    return _client


def get_trace_url(run_id: str) -> str:
    """Return the LangSmith UI URL for a given run ID."""
    settings = get_settings()
    project = settings.langsmith_project
    return f"https://smith.langchain.com/o/default/projects/p/{project}/r/{run_id}"


def track_token_usage(model: str, input_tokens: int, output_tokens: int, cost: float) -> dict:
    """Return token usage metadata dict for attaching to a LangSmith run."""
    return {
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "cost_usd": cost,
    }


def traced(name: str, metadata: dict | None = None):
    """Decorator: wraps any async or sync function with a LangSmith RunTree span."""
    def decorator(fn):
        @functools.wraps(fn)
        async def async_wrapper(*args, **kwargs):
            settings = get_settings()
            if not settings.langsmith_tracing:
                return await fn(*args, **kwargs)

            trace_id: str | None = kwargs.get("trace_id")
            if trace_id is None and args and isinstance(args[0], dict):
                trace_id = args[0].get("trace_id")

            run_meta = dict(metadata or {})
            if trace_id:
                run_meta["trace_id"] = trace_id

            run = RunTree(
                name=name,
                run_type="chain",
                inputs={"args": str(args)[:500], "kwargs": str(kwargs)[:500]},
                metadata=run_meta,
                project_name=settings.langsmith_project,
            )
            run.post()

            t0 = time.perf_counter()
            try:
                result = await fn(*args, **kwargs)
                latency_ms = (time.perf_counter() - t0) * 1000
                run.end(
                    outputs={"result": str(result)[:1000]},
                    metadata={**run_meta, "latency_ms": latency_ms},
                )
                run.patch()
                return result
            except Exception as exc:
                latency_ms = (time.perf_counter() - t0) * 1000
                run.end(
                    error=str(exc),
                    metadata={**run_meta, "latency_ms": latency_ms},
                )
                run.patch()
                raise

        @functools.wraps(fn)
        def sync_wrapper(*args, **kwargs):
            settings = get_settings()
            if not settings.langsmith_tracing:
                return fn(*args, **kwargs)

            trace_id: str | None = kwargs.get("trace_id")
            run_meta = dict(metadata or {})
            if trace_id:
                run_meta["trace_id"] = trace_id

            run = RunTree(
                name=name,
                run_type="chain",
                inputs={"args": str(args)[:500], "kwargs": str(kwargs)[:500]},
                metadata=run_meta,
                project_name=settings.langsmith_project,
            )
            run.post()

            t0 = time.perf_counter()
            try:
                result = fn(*args, **kwargs)
                latency_ms = (time.perf_counter() - t0) * 1000
                run.end(
                    outputs={"result": str(result)[:1000]},
                    metadata={**run_meta, "latency_ms": latency_ms},
                )
                run.patch()
                return result
            except Exception as exc:
                latency_ms = (time.perf_counter() - t0) * 1000
                run.end(
                    error=str(exc),
                    metadata={**run_meta, "latency_ms": latency_ms},
                )
                run.patch()
                raise

        if asyncio.iscoroutinefunction(fn):
            return async_wrapper
        return sync_wrapper

    return decorator


__all__: list[Any] = ["traced", "get_trace_url", "track_token_usage"]
