"""Per-session conversation memory in Redis.

Server-side working memory for multi-turn chat: the frontend sends a stable
session_id and the backend keeps the recent turns so the pipeline can resolve
follow-ups ("what about its failure modes?") and stay conversational. Stored as
a single JSON list under a session-namespaced key with a sliding TTL. Phase 2
will add a rolling summary of older turns; for now we keep the most recent
`_MAX_TURNS` verbatim.
"""
import json
from functools import lru_cache

from upstash_redis import Redis

from app.config import get_settings

_TTL = 60 * 60 * 24  # 24h, refreshed on every read/write (sliding)
_MAX_TURNS = 20  # most recent messages kept verbatim (Phase 2 summarizes overflow)


@lru_cache(maxsize=1)
def _redis() -> Redis:
    s = get_settings()
    return Redis(url=s.upstash_redis_rest_url, token=s.upstash_redis_rest_token)


def _turns_key(session_id: str) -> str:
    return f"session:{session_id}:turns"


async def load_history(session_id: str | None) -> list[dict]:
    """Return the recent turns for a session as [{role, content}, ...] (or [])."""
    if not session_id:
        return []
    r = _redis()
    key = _turns_key(session_id)
    raw = r.get(key)
    if not raw:
        return []
    r.expire(key, _TTL)  # sliding
    try:
        turns = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    return turns if isinstance(turns, list) else []


async def append_turns(
    session_id: str | None, user_content: str, assistant_content: str
) -> None:
    """Append a user+assistant exchange, capped to the most recent _MAX_TURNS."""
    if not session_id:
        return
    r = _redis()
    key = _turns_key(session_id)
    history = await load_history(session_id)
    history.append({"role": "user", "content": user_content})
    history.append({"role": "assistant", "content": assistant_content})
    history = history[-_MAX_TURNS:]
    r.set(key, json.dumps(history), ex=_TTL)
