"""Cache-store policy: only context-free answers are written to the global cache."""
import pytest

from app.agents import supervisor
from app.agents.query_rewriter import ClassifiedQuery
from app.agents.synthesizer import SynthesizedAnswer


def _state(*, history, summary, cache_hit=False):
    return {
        "query": "what is a harness?",
        "session_id": "s1",
        "history": history,
        "summary": summary,
        "standalone_query": "what is an agent harness?",
        "query_embedding": [0.1, 0.2],
        "classified": ClassifiedQuery(
            original="what is a harness?",
            rewritten="what is an agent harness?",
            intent="retrieval",
            reasoning="",
        ),
        "retrieval_results": [],
        "sql_result": None,
        "answer": SynthesizedAnswer(
            answer="A", sources=[], confidence=0.8, trace_id="t", latency_ms=1.0
        ),
        "trace_id": "t",
        "cache_hit": cache_hit,
        "error": None,
    }


@pytest.fixture
def captured_cache_set(monkeypatch):
    calls = []

    async def fake_cache_set(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(supervisor, "cache_set", fake_cache_set)
    return calls


async def test_context_free_answer_is_cached(captured_cache_set):
    await supervisor._node_cache_store(_state(history=[], summary=""))
    assert len(captured_cache_set) == 1
    # Keyed on the standalone query, raw aliased for instant re-asks.
    args, kwargs = captured_cache_set[0]
    assert args[0] == "what is an agent harness?"
    assert kwargs["alias_queries"] == ["what is a harness?"]


async def test_answer_with_history_is_not_cached(captured_cache_set):
    await supervisor._node_cache_store(
        _state(history=[{"role": "user", "content": "earlier"}], summary="")
    )
    assert captured_cache_set == []


async def test_answer_with_summary_is_not_cached(captured_cache_set):
    await supervisor._node_cache_store(
        _state(history=[], summary="we discussed harnesses")
    )
    assert captured_cache_set == []


async def test_cache_hit_is_not_restored(captured_cache_set):
    await supervisor._node_cache_store(
        _state(history=[], summary="", cache_hit=True)
    )
    assert captured_cache_set == []
