"""Verify sliding-window rate limiter using a fake Upstash Redis."""
import time

import pytest

from app.retrieval import rate_limiter


class FakeRedis:
    """Minimal in-memory stand-in for the Upstash REST Redis client.

    Implements just the ZSET ops the limiter touches.
    """

    def __init__(self):
        self.z: dict[str, dict[str, float]] = {}

    def zremrangebyscore(self, key, min_, max_):
        members = self.z.setdefault(key, {})
        lo = float("-inf") if min_ == "-inf" else float(min_)
        hi = float("inf") if max_ == "+inf" else float(max_)
        for m in [k for k, s in members.items() if lo <= s <= hi]:
            members.pop(m, None)

    def zcard(self, key):
        return len(self.z.get(key, {}))

    def zrange(self, key, start, stop, withscores=False):
        members = self.z.get(key, {})
        items = sorted(members.items(), key=lambda kv: kv[1])
        end = stop + 1 if stop >= 0 else None
        sliced = items[start:end] if end is not None else items[start:]
        return sliced if withscores else [m for m, _ in sliced]

    def zadd(self, key, mapping):
        members = self.z.setdefault(key, {})
        members.update(mapping)

    def expire(self, key, seconds):
        return True


@pytest.fixture
def fake_redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(rate_limiter, "_redis", lambda: fake)
    return fake


async def test_first_n_requests_allowed(fake_redis, monkeypatch):
    from app.config import get_settings
    s = get_settings()
    limit = s.rate_limit_rpm

    allowed = 0
    for _ in range(limit):
        r = await rate_limiter.check_rate_limit("user-a")
        if r.allowed:
            allowed += 1
    assert allowed == limit


async def test_overflow_rejected_with_retry_after(fake_redis):
    from app.config import get_settings
    s = get_settings()
    limit = s.rate_limit_rpm

    for _ in range(limit):
        await rate_limiter.check_rate_limit("user-b")

    r = await rate_limiter.check_rate_limit("user-b")
    assert not r.allowed
    assert r.remaining == 0
    assert r.reset_in > 0


async def test_separate_users_have_separate_buckets(fake_redis):
    from app.config import get_settings
    s = get_settings()
    limit = s.rate_limit_rpm

    # Fill user-c's bucket
    for _ in range(limit):
        await rate_limiter.check_rate_limit("user-c")

    overflow = await rate_limiter.check_rate_limit("user-c")
    assert not overflow.allowed

    # user-d should still be allowed
    other = await rate_limiter.check_rate_limit("user-d")
    assert other.allowed


async def test_window_expiry_resets_bucket(fake_redis, monkeypatch):
    from app.config import get_settings
    s = get_settings()
    limit = s.rate_limit_rpm

    # Fill the bucket with timestamps that look old
    now = time.time()
    fake_redis.z["ratelimit:user-e"] = {
        f"m{i}": now - s.rate_limit_window - 10 for i in range(limit)
    }

    # The next call should sweep them out and allow the request.
    r = await rate_limiter.check_rate_limit("user-e")
    assert r.allowed
