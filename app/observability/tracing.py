"""Per-hop LangSmith tracing wired into every agent node.

A tracing failure must NEVER affect the user-facing response. All LangSmith
calls are wrapped in try/except; a process-wide circuit breaker disables
tracing after `_FAIL_THRESHOLD` consecutive failures (LangSmith 401, network,
etc.) until the process restarts.
"""
import asyncio
import functools
import logging
import os
import threading
import time
from typing import Any

from langsmith import Client, RunTree

from app.config import get_settings

logger = logging.getLogger(__name__)

_client: Client | None = None

# ── Circuit breaker state ────────────────────────────────────────────────────
_FAIL_THRESHOLD = 3
_tracing_disabled: bool = False
_consecutive_failures: int = 0
_state_lock = threading.Lock()


def is_tracing_healthy() -> bool:
    """Return False once the circuit breaker has tripped this process."""
    return not _tracing_disabled


def _record_failure(exc: Exception) -> None:
    """Increment failure counter; trip the breaker at the threshold."""
    global _tracing_disabled, _consecutive_failures
    with _state_lock:
        _consecutive_failures += 1
        if _consecutive_failures >= _FAIL_THRESHOLD and not _tracing_disabled:
            _tracing_disabled = True
            logger.error(
                "Tracing circuit breaker tripped after %d consecutive failures; "
                "LangSmith calls disabled for process lifetime. Last error: %s",
                _consecutive_failures,
                exc,
            )
        else:
            logger.warning("LangSmith call failed (%d/%d): %s",
                           _consecutive_failures, _FAIL_THRESHOLD, exc)


def _record_success() -> None:
    """Reset the consecutive-failure counter on any successful call."""
    global _consecutive_failures
    with _state_lock:
        _consecutive_failures = 0


def _reset_circuit_breaker() -> None:
    """Test-only: reset the breaker state."""
    global _tracing_disabled, _consecutive_failures
    with _state_lock:
        _tracing_disabled = False
        _consecutive_failures = 0


def _get_client() -> Client:
    global _client
    if _client is None:
        settings = get_settings()
        os.environ.setdefault("LANGSMITH_API_KEY", settings.langsmith_api_key)
        os.environ.setdefault("LANGSMITH_PROJECT", settings.langsmith_project)
        _client = Client()
    return _client


def _safe_post(run: RunTree) -> None:
    """Post a run without ever raising. Records success/failure for the breaker."""
    if _tracing_disabled:
        return
    try:
        run.post()
        _record_success()
    except Exception as exc:  # noqa: BLE001 — tracing must never break the caller
        _record_failure(exc)


def _safe_patch(run: RunTree) -> None:
    """Patch (finalize) a run without ever raising."""
    if _tracing_disabled:
        return
    try:
        run.patch()
        _record_success()
    except Exception as exc:  # noqa: BLE001
        _record_failure(exc)


def _safe_end(run: RunTree, **kwargs: Any) -> None:
    """Mark a run ended without ever raising."""
    if _tracing_disabled:
        return
    try:
        run.end(**kwargs)
    except Exception as exc:  # noqa: BLE001
        _record_failure(exc)


def _build_run(name: str, args: tuple, kwargs: dict, run_meta: dict) -> RunTree | None:
    """Construct a RunTree; return None if construction itself fails."""
    if _tracing_disabled:
        return None
    try:
        settings = get_settings()
        return RunTree(
            name=name,
            run_type="chain",
            inputs={"args": str(args)[:500], "kwargs": str(kwargs)[:500]},
            metadata=run_meta,
            project_name=settings.langsmith_project,
        )
    except Exception as exc:  # noqa: BLE001
        _record_failure(exc)
        return None


# NOTE: get_trace_url is intentionally NOT exported. It used to be returned in
# API responses, which exposed every project trace to every authenticated user
# (data breach — see docs/audit/pre-deployment-report.md, issue 1.2). Use the
# raw `trace_id` UUID instead and resolve URLs inside LangSmith's UI directly.
def _get_trace_url_internal(run_id: str) -> str:
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
    """Decorator: wraps any async or sync function with a LangSmith RunTree span.

    Any LangSmith failure (401, network, etc.) is logged at WARNING and
    swallowed; the wrapped function always runs and its result/exception
    is returned/propagated unchanged. After `_FAIL_THRESHOLD` consecutive
    failures the circuit breaker trips and subsequent tracing calls are
    skipped entirely.
    """
    def decorator(fn):
        @functools.wraps(fn)
        async def async_wrapper(*args, **kwargs):
            settings = get_settings()
            if not settings.langsmith_tracing or _tracing_disabled:
                return await fn(*args, **kwargs)

            trace_id: str | None = kwargs.get("trace_id")
            if trace_id is None and args and isinstance(args[0], dict):
                trace_id = args[0].get("trace_id")

            run_meta = dict(metadata or {})
            if trace_id:
                run_meta["trace_id"] = trace_id

            run = _build_run(name, args, kwargs, run_meta)
            if run is not None:
                _safe_post(run)

            t0 = time.perf_counter()
            try:
                result = await fn(*args, **kwargs)
                latency_ms = (time.perf_counter() - t0) * 1000
                if run is not None:
                    _safe_end(run, outputs={"result": str(result)[:1000]},
                              metadata={**run_meta, "latency_ms": latency_ms})
                    _safe_patch(run)
                return result
            except Exception as exc:
                latency_ms = (time.perf_counter() - t0) * 1000
                if run is not None:
                    _safe_end(run, error=str(exc),
                              metadata={**run_meta, "latency_ms": latency_ms})
                    _safe_patch(run)
                raise

        @functools.wraps(fn)
        def sync_wrapper(*args, **kwargs):
            settings = get_settings()
            if not settings.langsmith_tracing or _tracing_disabled:
                return fn(*args, **kwargs)

            trace_id: str | None = kwargs.get("trace_id")
            run_meta = dict(metadata or {})
            if trace_id:
                run_meta["trace_id"] = trace_id

            run = _build_run(name, args, kwargs, run_meta)
            if run is not None:
                _safe_post(run)

            t0 = time.perf_counter()
            try:
                result = fn(*args, **kwargs)
                latency_ms = (time.perf_counter() - t0) * 1000
                if run is not None:
                    _safe_end(run, outputs={"result": str(result)[:1000]},
                              metadata={**run_meta, "latency_ms": latency_ms})
                    _safe_patch(run)
                return result
            except Exception as exc:
                latency_ms = (time.perf_counter() - t0) * 1000
                if run is not None:
                    _safe_end(run, error=str(exc),
                              metadata={**run_meta, "latency_ms": latency_ms})
                    _safe_patch(run)
                raise

        if asyncio.iscoroutinefunction(fn):
            return async_wrapper
        return sync_wrapper

    return decorator


__all__: list[Any] = ["traced", "track_token_usage", "is_tracing_healthy"]
