"""Per-session conversation memory in Redis: recent turns + a rolling summary.

Server-side working memory for multi-turn chat. The frontend sends a stable
session_id; the backend keeps the recent turns verbatim and, once they exceed
the token budget, folds the oldest into a rolling summary (via an injected
summarizer callback, so this module stays LLM-free). The pipeline gets both the
summary and the recent turns to resolve follow-ups and stay conversational.
Stored under session-namespaced keys with a sliding TTL.
"""
import json
from collections.abc import Awaitable, Callable
from functools import lru_cache
from typing import NamedTuple

from upstash_redis import Redis

from app.config import get_settings

_TTL = 60 * 60 * 24  # 24h, refreshed on every read/write (sliding)
_KEEP_RECENT = 4  # messages kept verbatim after a summarization fold (2 exchanges)
_HARD_CAP = 20  # absolute cap on stored messages (bounds storage if summary fails)

Summarizer = Callable[[str, list[dict]], Awaitable[str]]


class Memory(NamedTuple):
    summary: str
    turns: list[dict]


@lru_cache(maxsize=1)
def _redis() -> Redis:
    s = get_settings()
    return Redis(url=s.upstash_redis_rest_url, token=s.upstash_redis_rest_token)


def _turns_key(session_id: str) -> str:
    return f"session:{session_id}:turns"


def _summary_key(session_id: str) -> str:
    return f"session:{session_id}:summary"


def _estimate_tokens(turns: list[dict]) -> int:
    # Char/4 heuristic — avoids a tiktoken vocab download at runtime (distroless)
    # and is plenty precise for a budget threshold.
    return sum(len(t.get("content") or "") for t in turns) // 4


async def load_memory(session_id: str | None) -> Memory:
    """Return (rolling summary, recent turns) for a session."""
    if not session_id:
        return Memory("", [])
    r = _redis()
    tk, sk = _turns_key(session_id), _summary_key(session_id)
    turns_raw = r.get(tk)
    summary = r.get(sk) or ""
    if turns_raw:
        r.expire(tk, _TTL)
    if summary:
        r.expire(sk, _TTL)
    try:
        turns = json.loads(turns_raw) if turns_raw else []
        if not isinstance(turns, list):
            turns = []
    except (json.JSONDecodeError, TypeError):
        turns = []
    return Memory(summary, turns)


async def load_history(session_id: str | None) -> list[dict]:
    """Convenience: just the recent turns (without the summary)."""
    return (await load_memory(session_id)).turns


async def append_turns(
    session_id: str | None,
    user_content: str,
    assistant_content: str,
    *,
    summarize: Summarizer | None = None,
) -> None:
    """Append a user+assistant exchange. When the recent turns exceed the token
    budget, fold the oldest into the rolling summary via `summarize` (if given)."""
    if not session_id:
        return
    r = _redis()
    mem = await load_memory(session_id)
    turns = [
        *mem.turns,
        {"role": "user", "content": user_content},
        {"role": "assistant", "content": assistant_content},
    ]
    summary = mem.summary
    budget = get_settings().memory_token_budget

    if (
        summarize is not None
        and len(turns) > _KEEP_RECENT
        and _estimate_tokens(turns) > budget
    ):
        overflow = turns[:-_KEEP_RECENT]
        try:
            summary = await summarize(summary, overflow)
            r.set(_summary_key(session_id), summary, ex=_TTL)
            turns = turns[-_KEEP_RECENT:]
        except Exception:
            pass  # summarization failed — fall through to the hard cap

    turns = turns[-_HARD_CAP:]  # bound storage even if summarization didn't run
    r.set(_turns_key(session_id), json.dumps(turns), ex=_TTL)
