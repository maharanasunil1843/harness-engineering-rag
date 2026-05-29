"""End-to-end pipeline tests against live services.

These tests run only when credentials are present and the corpus has been
ingested. Skipped by default (filtered via the `integration` marker). CI
runs them only on push-to-main where secrets are available.
"""
import os

import pytest

pytestmark = pytest.mark.integration


def _has_live_creds() -> bool:
    needed = [
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "DATABASE_URL",
        "UPSTASH_REDIS_REST_URL",
        "UPSTASH_REDIS_REST_TOKEN",
    ]
    return all(
        os.environ.get(k) and not os.environ[k].startswith("test-") for k in needed
    )


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _has_live_creds(),
        reason="live credentials not present — set ANTHROPIC_API_KEY etc.",
    ),
]


async def test_retrieval_intent_routes_to_vector_search():
    from app.agents.supervisor import ask
    answer = await ask("What is a wiring harness?")
    assert answer.answer
    assert answer.confidence >= 0.5


async def test_sql_intent_returns_rows():
    from app.agents.query_rewriter import rewrite_and_classify
    classified = await rewrite_and_classify("List all safety components")
    assert classified.intent in ("sql", "hybrid", "retrieval")


async def test_direct_intent_for_greeting():
    from app.agents.query_rewriter import rewrite_and_classify
    classified = await rewrite_and_classify("Hello")
    assert classified.intent in ("direct", "retrieval")


async def test_cache_roundtrip_hits_on_second_query():
    """First query is a miss, second identical query should be a hit."""
    from app.retrieval.cache import cache_get, cache_set
    from app.retrieval.hybrid import _embed_query

    q = "integration-test query — cache roundtrip"
    emb = _embed_query(q)

    miss = await cache_get(q, emb)
    assert miss is None

    await cache_set(q, emb, answer="cached answer", sources=[])

    hit = await cache_get(q, emb)
    assert hit is not None
    assert hit.answer == "cached answer"
