"""Redis-based sliding-window rate limiter."""
import time

from pydantic import BaseModel
from upstash_redis import Redis

from app.config import get_settings


class RateLimitResult(BaseModel):
    allowed: bool
    remaining: int
    reset_in: float


def _redis() -> Redis:
    s = get_settings()
    return Redis(url=s.upstash_redis_rest_url, token=s.upstash_redis_rest_token)


async def check_rate_limit(user_id: str = "default") -> RateLimitResult:
    s = get_settings()
    r = _redis()

    key = f"ratelimit:{user_id}"
    now = time.time()
    window_start = now - s.rate_limit_window
    limit = s.rate_limit_rpm

    # Remove members older than the window
    r.zremrangebyscore(key, "-inf", window_start)

    # Count current members in window
    count = r.zcard(key)

    if count >= limit:
        # Oldest member score = time of oldest request in window
        oldest = r.zrange(key, 0, 0, withscores=True)
        reset_in = (oldest[0][1] + s.rate_limit_window - now) if oldest else float(s.rate_limit_window)
        return RateLimitResult(allowed=False, remaining=0, reset_in=max(0.0, reset_in))

    # Add current request
    member = str(now)
    r.zadd(key, {member: now})
    r.expire(key, s.rate_limit_window * 2)

    remaining = max(0, limit - count - 1)
    return RateLimitResult(allowed=True, remaining=remaining, reset_in=0.0)
