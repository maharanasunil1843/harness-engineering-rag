"""Semantic cache via Upstash Redis with embedding-similarity lookup.

CACHE KEYING IS GLOBAL — not per user. User A's query can return a hit on
user B's cached answer. For this corpus this is acceptable because:
  - The harness engineering corpus is public-domain reference material.
  - No user-specific data flows into a query or answer.
  - Per-user keying would gut the hit rate (the whole point of semantic
    cache is to share results across the same question phrased differently).
If this service ever ingests user-specific data, change the index/entry keys
to namespace by user id and reset cache_stats accordingly.
"""
import json
import math
import time
from uuid import uuid4

from pydantic import BaseModel
from upstash_redis import Redis

from app.config import get_settings

# Production: use a vector index (Redis VSS module or a dedicated embedding store)
# for sub-linear lookup. Linear scan is O(n) and acceptable below ~5000 entries.
_INDEX_KEY = "cache:index"
_HITS_KEY = "cache:hits"
_MISSES_KEY = "cache:misses"


class CacheResult(BaseModel):
    answer: str
    sources: list[dict]
    similarity: float
    cached_query: str


def _redis() -> Redis:
    s = get_settings()
    return Redis(url=s.upstash_redis_rest_url, token=s.upstash_redis_rest_token)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def cache_get(query: str, query_embedding: list[float]) -> CacheResult | None:
    s = get_settings()
    r = _redis()
    threshold = s.cache_similarity_threshold

    entry_keys = r.smembers(_INDEX_KEY)
    if not entry_keys:
        r.incr(_MISSES_KEY)
        return None

    best: CacheResult | None = None
    best_sim = -1.0

    for key in entry_keys:
        raw = r.get(key)
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
            if sim >= threshold:
                best = CacheResult(
                    answer=entry["answer"],
                    sources=entry.get("sources", []),
                    similarity=sim,
                    cached_query=entry.get("query", ""),
                )

    if best is not None:
        r.incr(_HITS_KEY)
        return best

    r.incr(_MISSES_KEY)
    return None


async def cache_set(
    query: str,
    query_embedding: list[float],
    answer: str,
    sources: list[dict],
) -> None:
    s = get_settings()
    r = _redis()

    entry_key = f"cache:entry:{uuid4()}"
    payload = json.dumps(
        {
            "query": query,
            "embedding": query_embedding,
            "answer": answer,
            "sources": sources,
            "timestamp": time.time(),
        }
    )
    r.set(entry_key, payload)
    r.expire(entry_key, s.cache_ttl)
    r.sadd(_INDEX_KEY, entry_key)


async def cache_stats() -> dict:
    r = _redis()
    entries = r.scard(_INDEX_KEY) or 0
    hits = int(r.get(_HITS_KEY) or 0)
    misses = int(r.get(_MISSES_KEY) or 0)
    total = hits + misses
    hit_rate = hits / total if total > 0 else 0.0
    return {"entries": entries, "hits": hits, "misses": misses, "hit_rate": hit_rate}
