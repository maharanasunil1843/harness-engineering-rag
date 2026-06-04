"""Verify cache primitives and stats accounting."""
import math
import random
from types import SimpleNamespace

import pytest

from app.retrieval import cache
from app.retrieval.cache import _cosine, _exact_key, _normalize


def test_cosine_identical_vectors_is_one():
    v = [1.0, 2.0, 3.0, 4.0]
    assert math.isclose(_cosine(v, v), 1.0, rel_tol=1e-9)


def test_cosine_orthogonal_vectors_is_zero():
    a = [1.0, 0.0]
    b = [0.0, 1.0]
    assert math.isclose(_cosine(a, b), 0.0, abs_tol=1e-9)


def test_cosine_opposite_vectors_is_negative_one():
    a = [1.0, 2.0, 3.0]
    b = [-1.0, -2.0, -3.0]
    assert math.isclose(_cosine(a, b), -1.0, rel_tol=1e-9)


def test_cosine_zero_vector_returns_zero():
    a = [0.0, 0.0, 0.0]
    b = [1.0, 2.0, 3.0]
    assert _cosine(a, b) == 0.0
    assert _cosine(b, a) == 0.0


def test_cosine_random_vectors_in_range():
    rng = random.Random(42)
    a = [rng.uniform(-1, 1) for _ in range(128)]
    b = [rng.uniform(-1, 1) for _ in range(128)]
    sim = _cosine(a, b)
    assert -1.0 <= sim <= 1.0


def test_cosine_high_similarity_for_near_duplicates():
    rng = random.Random(7)
    a = [rng.uniform(-1, 1) for _ in range(1536)]
    # b is a with 1% noise — should still be highly similar.
    b = [x + rng.uniform(-0.01, 0.01) for x in a]
    sim = _cosine(a, b)
    assert sim > 0.99


# ── Key normalization ────────────────────────────────────────────────────────

def test_normalize_lowercases_and_collapses_whitespace():
    assert _normalize("  What   IS a\tHarness?  ") == "what is a harness?"


def test_exact_key_is_normalized_and_stable():
    # Differently-cased/spaced phrasings of the same question collide on purpose.
    assert _exact_key("What is a harness?") == _exact_key("  what  is a HARNESS? ")
    assert _exact_key("a") != _exact_key("b")
    assert _exact_key("x").startswith("cache:exact:")


# ── cache_get / cache_set against an in-memory fake Redis ────────────────────

class FakeRedis:
    """Minimal in-memory stand-in for the Upstash REST client (test-only)."""

    def __init__(self) -> None:
        self.kv: dict[str, str] = {}
        self.sets: dict[str, set] = {}
        self.counters: dict[str, int] = {}

    async def get(self, k):
        return self.kv.get(k)

    async def set(self, k, v, ex=None, **kw):
        self.kv[k] = v

    async def delete(self, *keys):
        for k in keys:
            self.kv.pop(k, None)

    async def mget(self, *keys):
        return [self.kv.get(k) for k in keys]

    async def sadd(self, key, *members):
        self.sets.setdefault(key, set()).update(members)

    async def srem(self, key, *members):
        s = self.sets.get(key, set())
        for m in members:
            s.discard(m)

    async def smembers(self, key):
        return list(self.sets.get(key, set()))

    async def scard(self, key):
        return len(self.sets.get(key, set()))

    async def incr(self, key):
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    async def expire(self, key, seconds, **kw):
        return True


@pytest.fixture
def fake_cache(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(cache, "_redis", lambda: fake)
    monkeypatch.setattr(
        cache,
        "get_settings",
        lambda: SimpleNamespace(
            cache_ttl=3600,
            cache_similarity_threshold=0.92,
            upstash_redis_rest_url="x",
            upstash_redis_rest_token="y",
        ),
    )
    return fake


async def test_exact_match_ignores_embedding(fake_cache):
    await cache.cache_set("What is a harness?", [0.1] * 8, "ANS", [{"x": 1}], 0.8)
    # Re-ask with different casing/spacing AND a useless embedding: the exact
    # fast path must still hit (similarity 1.0) without the semantic scan.
    res = await cache.cache_get("  what is a HARNESS? ", [0.0] * 8)
    assert res is not None
    assert res.similarity == 1.0
    assert res.answer == "ANS"
    assert res.confidence == 0.8


async def test_semantic_hit_above_threshold_and_miss_below(fake_cache):
    await cache.cache_set("alpha query", [1.0, 0.0, 0.0], "A", [], 0.7)
    hit = await cache.cache_get("different phrasing", [0.99, 0.01, 0.0])
    assert hit is not None and hit.answer == "A"
    miss = await cache.cache_get("different phrasing", [0.0, 1.0, 0.0])
    assert miss is None


async def test_orphan_index_member_is_reaped(fake_cache):
    # A dead entry key lingering in the index (entry expired, membership didn't).
    fake_cache.sets[cache._INDEX_KEY] = {"cache:entry:dead"}
    res = await cache.cache_get("anything", [0.1, 0.2, 0.3])
    assert res is None
    assert "cache:entry:dead" not in fake_cache.sets.get(cache._INDEX_KEY, set())


async def test_serializes_non_json_native_values(fake_cache):
    from decimal import Decimal

    # SQL rows carry Decimal/etc — default=str must keep cache_set from raising
    # (the old json.dumps silently dropped these writes).
    sources = [{"rows": [{"count": Decimal("42")}]}]
    await cache.cache_set("count things", [0.5, 0.5], "forty-two", sources, 0.9)
    res = await cache.cache_get("count things", [0.5, 0.5])
    assert res is not None
    assert res.answer == "forty-two"


# ── Banded acceptance (trust / gray-zone verify / floor) ─────────────────────
# Stored embedding is [1, 0]; query vectors are chosen for exact cosines:
#   [1, 0]        -> 1.00  (>= trust)
#   [0.7, 0.714]  -> 0.70  (gray zone: floor <= sim < trust)
#   [0.5, 0.866]  -> 0.50  (< floor)
_TRUST = 0.88
_FLOOR = 0.62


async def test_band_trust_accepts_without_verify(fake_cache):
    await cache.cache_set("q", [1.0, 0.0], "A", [], 0.7)
    calls = []

    async def verify(_q, _a):
        calls.append(1)
        return False

    hit = await cache.cache_get(
        "other", [1.0, 0.0], check_exact=False,
        verify=verify, trust_threshold=_TRUST, floor_threshold=_FLOOR,
    )
    assert hit is not None and hit.answer == "A"
    assert calls == []  # trust band must not invoke the verifier


async def test_band_gray_zone_verify_true_hits(fake_cache):
    await cache.cache_set("q", [1.0, 0.0], "A", [], 0.7)

    async def verify(_q, _a):
        return True

    hit = await cache.cache_get(
        "other", [0.7, 0.714], check_exact=False,
        verify=verify, trust_threshold=_TRUST, floor_threshold=_FLOOR,
    )
    assert hit is not None and hit.answer == "A"


async def test_band_gray_zone_verify_false_misses(fake_cache):
    await cache.cache_set("q", [1.0, 0.0], "A", [], 0.7)

    async def verify(_q, _a):
        return False

    hit = await cache.cache_get(
        "other", [0.7, 0.714], check_exact=False,
        verify=verify, trust_threshold=_TRUST, floor_threshold=_FLOOR,
    )
    assert hit is None


async def test_band_below_floor_misses_without_verify(fake_cache):
    await cache.cache_set("q", [1.0, 0.0], "A", [], 0.7)
    calls = []

    async def verify(_q, _a):
        calls.append(1)
        return True

    hit = await cache.cache_get(
        "other", [0.5, 0.866], check_exact=False,
        verify=verify, trust_threshold=_TRUST, floor_threshold=_FLOOR,
    )
    assert hit is None
    assert calls == []  # below floor must not invoke the verifier
