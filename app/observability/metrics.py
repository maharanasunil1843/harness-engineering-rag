"""In-process metrics for query traffic.

Works without LangSmith — production would push these to Prometheus or
CloudWatch. The store is thread-safe via a single lock; latencies are kept
in a bounded deque so memory is constant.
"""
from __future__ import annotations

import threading
from collections import deque
from typing import Any

# Bounded so a long-running process doesn't grow unbounded.
_LATENCY_WINDOW = 1000


class _MetricsStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._query_count = 0
        self._cache_hits = 0
        self._cache_misses = 0
        self._error_count = 0
        self._routing_distribution: dict[str, int] = {}
        self._latencies_ms: deque[float] = deque(maxlen=_LATENCY_WINDOW)
        self._total_tokens = 0
        self._total_cost_usd = 0.0

    def record_query(
        self,
        intent: str,
        latency_ms: float,
        cache_hit: bool,
        tokens: int,
        cost: float,
        error: bool,
    ) -> None:
        with self._lock:
            self._query_count += 1
            if cache_hit:
                self._cache_hits += 1
            else:
                self._cache_misses += 1
            if error:
                self._error_count += 1
            self._routing_distribution[intent] = (
                self._routing_distribution.get(intent, 0) + 1
            )
            self._latencies_ms.append(float(latency_ms))
            self._total_tokens += int(tokens)
            self._total_cost_usd += float(cost)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            sorted_lat = sorted(self._latencies_ms)
            n = len(sorted_lat)
            total = self._cache_hits + self._cache_misses
            return {
                "query_count": self._query_count,
                "cache_hits": self._cache_hits,
                "cache_misses": self._cache_misses,
                "cache_hit_rate": (self._cache_hits / total) if total else 0.0,
                "routing_distribution": dict(self._routing_distribution),
                "error_count": self._error_count,
                "p50_latency_ms": _percentile(sorted_lat, 50, n),
                "p95_latency_ms": _percentile(sorted_lat, 95, n),
                "total_tokens_used": self._total_tokens,
                "estimated_cost_usd": round(self._total_cost_usd, 6),
                "latency_window_size": n,
            }

    def reset(self) -> None:
        with self._lock:
            self._query_count = 0
            self._cache_hits = 0
            self._cache_misses = 0
            self._error_count = 0
            self._routing_distribution.clear()
            self._latencies_ms.clear()
            self._total_tokens = 0
            self._total_cost_usd = 0.0


def _percentile(sorted_values: list[float], p: int, n: int) -> float:
    if n == 0:
        return 0.0
    # Nearest-rank percentile — adequate for an observability snapshot.
    idx = max(0, min(n - 1, int(round((p / 100) * n)) - 1))
    return round(sorted_values[idx], 2)


_store = _MetricsStore()


def record_query(
    intent: str,
    latency_ms: float,
    cache_hit: bool,
    tokens: int,
    cost: float,
    error: bool,
) -> None:
    _store.record_query(intent, latency_ms, cache_hit, tokens, cost, error)


def get_metrics_snapshot() -> dict[str, Any]:
    return _store.snapshot()


def reset_metrics() -> None:
    """Test-only helper."""
    _store.reset()


__all__ = ["record_query", "get_metrics_snapshot", "reset_metrics"]
