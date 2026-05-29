"""Verify tracing circuit breaker and metrics accounting."""
import pytest

from app.observability import metrics as metrics_mod
from app.observability import tracing


@pytest.fixture(autouse=True)
def _reset_state():
    tracing._reset_circuit_breaker()
    metrics_mod.reset_metrics()
    yield
    tracing._reset_circuit_breaker()
    metrics_mod.reset_metrics()


# ── tracing decorator ────────────────────────────────────────────────────────

async def test_tracing_failure_does_not_propagate(monkeypatch):
    """A LangSmith failure inside _safe_post must not raise to the caller."""

    # Force _build_run to return a RunTree that raises on post().
    class BadRun:
        def post(self):
            raise RuntimeError("simulated LangSmith 401")

        def patch(self):
            raise RuntimeError("simulated LangSmith 401")

        def end(self, **_):
            raise RuntimeError("simulated LangSmith 401")

    monkeypatch.setattr(tracing, "_build_run", lambda *a, **kw: BadRun())
    monkeypatch.setattr(
        tracing, "get_settings",
        lambda: type("S", (), {"langsmith_tracing": True, "langsmith_project": "p"})(),
    )

    @tracing.traced("test-node")
    async def my_fn(x):
        return x * 2

    # Must complete normally even though every LangSmith call raises.
    result = await my_fn(21)
    assert result == 42


def test_circuit_breaker_trips_after_three_failures():
    assert tracing.is_tracing_healthy()
    for _ in range(3):
        tracing._record_failure(Exception("nope"))
    assert not tracing.is_tracing_healthy()


def test_circuit_breaker_does_not_trip_at_two_failures():
    tracing._record_failure(Exception("nope"))
    tracing._record_failure(Exception("nope"))
    assert tracing.is_tracing_healthy()


def test_success_resets_failure_counter():
    tracing._record_failure(Exception("nope"))
    tracing._record_failure(Exception("nope"))
    tracing._record_success()
    # After a success, two more failures should NOT trip the breaker.
    tracing._record_failure(Exception("nope"))
    tracing._record_failure(Exception("nope"))
    assert tracing.is_tracing_healthy()


def test_disabled_breaker_skips_post(monkeypatch):
    posted = []

    class TrackRun:
        def post(self):
            posted.append(1)

        def patch(self):
            pass

        def end(self, **_):
            pass

    tracing._record_failure(Exception("e1"))
    tracing._record_failure(Exception("e2"))
    tracing._record_failure(Exception("e3"))
    assert not tracing.is_tracing_healthy()

    tracing._safe_post(TrackRun())
    assert posted == []


# ── metrics ─────────────────────────────────────────────────────────────────

def test_record_query_updates_counts():
    metrics_mod.record_query(
        intent="retrieval", latency_ms=120.0,
        cache_hit=False, tokens=100, cost=0.001, error=False,
    )
    snap = metrics_mod.get_metrics_snapshot()
    assert snap["query_count"] == 1
    assert snap["cache_misses"] == 1
    assert snap["cache_hits"] == 0
    assert snap["routing_distribution"] == {"retrieval": 1}
    assert snap["total_tokens_used"] == 100
    assert snap["error_count"] == 0


def test_record_query_tracks_cache_hits():
    metrics_mod.record_query(
        intent="direct", latency_ms=5.0,
        cache_hit=True, tokens=0, cost=0.0, error=False,
    )
    snap = metrics_mod.get_metrics_snapshot()
    assert snap["cache_hits"] == 1
    assert snap["cache_hit_rate"] == 1.0


def test_record_query_tracks_errors():
    metrics_mod.record_query(
        intent="error", latency_ms=42.0,
        cache_hit=False, tokens=0, cost=0.0, error=True,
    )
    snap = metrics_mod.get_metrics_snapshot()
    assert snap["error_count"] == 1


def test_record_query_routing_distribution():
    metrics_mod.record_query("retrieval", 1.0, False, 0, 0.0, False)
    metrics_mod.record_query("retrieval", 1.0, False, 0, 0.0, False)
    metrics_mod.record_query("sql", 1.0, False, 0, 0.0, False)
    metrics_mod.record_query("hybrid", 1.0, False, 0, 0.0, False)
    snap = metrics_mod.get_metrics_snapshot()
    assert snap["routing_distribution"]["retrieval"] == 2
    assert snap["routing_distribution"]["sql"] == 1
    assert snap["routing_distribution"]["hybrid"] == 1


def test_get_metrics_snapshot_latency_percentiles():
    for ms in [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]:
        metrics_mod.record_query("retrieval", float(ms), False, 0, 0.0, False)
    snap = metrics_mod.get_metrics_snapshot()
    assert snap["p50_latency_ms"] > 0
    assert snap["p95_latency_ms"] >= snap["p50_latency_ms"]


def test_reset_metrics_zeros_everything():
    metrics_mod.record_query("retrieval", 1.0, True, 0, 0.0, False)
    metrics_mod.reset_metrics()
    snap = metrics_mod.get_metrics_snapshot()
    assert snap["query_count"] == 0
    assert snap["cache_hits"] == 0
    assert snap["cache_misses"] == 0
    assert snap["routing_distribution"] == {}
