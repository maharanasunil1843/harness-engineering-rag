"""Semantic cache via Upstash Redis with embedding-similarity lookup.

CACHE KEYING IS GLOBAL — not per user. User A's query can return a hit on
user B's cached answer. For this corpus this is acceptable because:
  - The harness engineering corpus is public-domain reference material.
  - No user-specific data flows into a query or answer.
  - Per-user keying would gut the hit rate (the whole point of semantic
    cache is to share results across the same question phrased differently).
If this service ever ingests user-specific data, change the index/entry keys
to namespace by user id and reset cache_stats accordingly.

LOOKUP PATH (latency-tuned):
  1. Exact-match fast path — sha256 of the normalized query maps straight to an
     entry. O(1), skips the embedding scan entirely for identical re-asks.
  2. Semantic scan — a single MGET pulls every candidate in one round-trip
     (Upstash is a REST API; the old per-entry GET loop was O(n) round-trips),
     then cosine similarity ranks them. Dead index members (expired entries)
     are SREM'd as they're discovered, so the index can't grow unbounded.
On any hit the entry's TTL is refreshed (sliding expiration), so popular
answers persist and cold ones age out.
"""
import hashlib
import json
import math
import time
from collections.abc import Awaitable, Callable
from functools import lru_cache
from uuid import uuid4

from pydantic import BaseModel
from upstash_redis.asyncio import Redis

from app.config import get_settings

# Production: use a vector index (Upstash Vector or Redis VSS) for sub-linear
# lookup. A single-MGET linear scan is acceptable below ~5000 live entries.
_INDEX_KEY = "cache:index"
_HITS_KEY = "cache:hits"
_MISSES_KEY = "cache:misses"
_EXACT_PREFIX = "cache:exact:"
_MGET_BATCH = 128  # cap per MGET so one request can't balloon past REST limits


class CacheResult(BaseModel):
    answer: str
    sources: list[dict]
    similarity: float
    cached_query: str
    # Confidence parsed at original synthesis time. Defaults to 0.5 (the
    # synthesizer's own fallback) for legacy entries cached before this field
    # existed, rather than the misleading 1.0 the supervisor used to hard-code.
    confidence: float = 0.5


@lru_cache(maxsize=1)
def _redis() -> Redis:
    # Reuse a single client across calls — each Redis() is just a thin REST
    # wrapper, but re-creating one per lookup was needless churn.
    s = get_settings()
    return Redis(url=s.upstash_redis_rest_url, token=s.upstash_redis_rest_token)


def _normalize(query: str) -> str:
    return " ".join(query.lower().split())


def _exact_key(query: str) -> str:
    digest = hashlib.sha256(_normalize(query).encode()).hexdigest()
    return f"{_EXACT_PREFIX}{digest}"


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def _mget_all(r: Redis, keys: list[str]) -> dict[str, str | None]:
    """MGET keys in batches; return {key: raw_value_or_None} preserving misses."""
    out: dict[str, str | None] = {}
    for i in range(0, len(keys), _MGET_BATCH):
        batch = keys[i : i + _MGET_BATCH]
        values = await r.mget(*batch)
        for k, v in zip(batch, values):
            out[k] = v
    return out


def _result_from_entry(entry: dict, similarity: float) -> CacheResult:
    return CacheResult(
        answer=entry["answer"],
        sources=entry.get("sources", []),
        similarity=similarity,
        cached_query=entry.get("query", ""),
        confidence=entry.get("confidence", 0.5),
    )


async def cache_get_exact(query: str) -> CacheResult | None:
    """O(1) exact-match lookup (normalized query -> entry); no embedding needed.

    Returns None on miss WITHOUT recording a miss — callers fall through to the
    semantic scan, which records the hit/miss for the request.
    """
    s = get_settings()
    r = _redis()
    ttl = s.cache_ttl
    ekey = _exact_key(query)
    mapped = await r.get(ekey)
    if not mapped:
        return None
    raw = await r.get(mapped)
    if raw:
        try:
            entry = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
        await r.expire(mapped, ttl)  # sliding TTL
        await r.expire(ekey, ttl)
        await r.incr(_HITS_KEY)
        return _result_from_entry(entry, 1.0)
    # Mapping outlived its entry — clean both up.
    await r.srem(_INDEX_KEY, mapped)
    await r.delete(ekey)
    return None


async def cache_get(
    query: str,
    query_embedding: list[float],
    *,
    check_exact: bool = True,
    count_miss: bool = True,
    verify: Callable[[str, str], Awaitable[bool]] | None = None,
    trust_threshold: float | None = None,
    floor_threshold: float | None = None,
) -> CacheResult | None:
    # count_miss=False lets a caller that will fall through to another cache
    # check (e.g. the stream handler -> ask()) avoid double-counting the miss.
    #
    # Banded acceptance: similarity >= trust is accepted outright; a candidate in
    # [floor, trust) is accepted only if verify(query, answer) returns True (a
    # cheap LLM check that the cached answer addresses the new question); below
    # floor is a miss. Defaults collapse to the old single-threshold behavior
    # (floor == trust == cache_similarity_threshold), so existing callers are
    # unaffected.
    s = get_settings()
    r = _redis()
    ttl = s.cache_ttl
    trust = (
        trust_threshold
        if trust_threshold is not None
        else s.cache_similarity_threshold
    )
    floor = floor_threshold if floor_threshold is not None else trust

    # 1) Exact-match fast path — O(1), no embedding scan. Callers that already
    #    ran cache_get_exact pass check_exact=False to skip the duplicate GET.
    if check_exact:
        exact = await cache_get_exact(query)
        if exact is not None:
            return exact

    # 2) Semantic scan — single MGET, then cosine rank.
    entry_keys = list(await r.smembers(_INDEX_KEY))
    if not entry_keys:
        if count_miss:
            await r.incr(_MISSES_KEY)
        return None

    values = await _mget_all(r, entry_keys)

    # Reap expired/dead index members so the scan stays bounded.
    orphans = [k for k, v in values.items() if v is None]
    if orphans:
        await r.srem(_INDEX_KEY, *orphans)

    best_entry: dict | None = None
    best_key: str | None = None
    best_sim = -1.0

    for key, raw in values.items():
        if raw is None:
            continue
        try:
            entry = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        stored_emb: list[float] = entry.get("embedding", [])
        if not stored_emb:
            continue
        sim = _cosine(query_embedding, stored_emb)
        if sim > best_sim:
            best_sim = sim
            best_entry = entry
            best_key = key

    if best_entry is not None and best_key is not None and best_sim >= floor:
        accept = best_sim >= trust
        if not accept and verify is not None:
            accept = await verify(query, best_entry["answer"])
        if accept:
            await r.expire(best_key, ttl)  # sliding TTL on the winner
            await r.incr(_HITS_KEY)
            return _result_from_entry(best_entry, best_sim)

    if count_miss:
        await r.incr(_MISSES_KEY)
    return None


async def cache_set(
    query: str,
    query_embedding: list[float],
    answer: str,
    sources: list[dict],
    confidence: float = 0.5,
    *,
    alias_queries: list[str] | None = None,
) -> None:
    """Store an answer keyed on `query`. `alias_queries` get their own exact-match
    keys pointing at the same entry — used to alias a first-turn raw query to its
    standalone form, while a follow-up (context-dependent raw text) is keyed only
    on the standalone query."""
    s = get_settings()
    r = _redis()
    ttl = s.cache_ttl

    entry_key = f"cache:entry:{uuid4()}"
    # default=str so non-JSON-native values from the SQL path (Decimal, datetime)
    # serialize instead of raising and silently dropping the write.
    payload = json.dumps(
        {
            "query": query,
            "embedding": query_embedding,
            "answer": answer,
            "sources": sources,
            "confidence": confidence,
            "timestamp": time.time(),
        },
        default=str,
    )
    # ex=ttl sets value + expiry in one round-trip (vs a separate EXPIRE).
    await r.set(entry_key, payload, ex=ttl)
    await r.sadd(_INDEX_KEY, entry_key)
    # Exact-match keys → entry, for the O(1) re-ask fast path. De-dup so the
    # canonical query and an identical alias aren't written twice.
    for q in {query, *(alias_queries or [])}:
        await r.set(_exact_key(q), entry_key, ex=ttl)


async def cache_stats() -> dict:
    r = _redis()
    entries = await r.scard(_INDEX_KEY) or 0
    hits = int(await r.get(_HITS_KEY) or 0)
    misses = int(await r.get(_MISSES_KEY) or 0)
    total = hits + misses
    hit_rate = hits / total if total > 0 else 0.0
    return {"entries": entries, "hits": hits, "misses": misses, "hit_rate": hit_rate}
