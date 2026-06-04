"""Session memory: load/append, hard cap, and rolling-summary fold."""
from types import SimpleNamespace

import pytest

from app.retrieval import session_memory as sm


class FakeRedis:
    def __init__(self) -> None:
        self.kv: dict[str, str] = {}

    async def get(self, k):
        return self.kv.get(k)

    async def set(self, k, v, ex=None, **kw):
        self.kv[k] = v

    async def expire(self, k, seconds, **kw):
        return True


def _settings(budget: int):
    return SimpleNamespace(
        memory_token_budget=budget,
        upstash_redis_rest_url="x",
        upstash_redis_rest_token="y",
    )


@pytest.fixture
def fake_mem(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(sm, "_redis", lambda: fake)
    # Large budget by default so summarization doesn't trigger unless asked.
    monkeypatch.setattr(sm, "get_settings", lambda: _settings(100000))
    return fake


async def test_load_empty_session_returns_empty(fake_mem):
    mem = await sm.load_memory("s1")
    assert mem.summary == "" and mem.turns == []
    assert await sm.load_memory(None) == sm.Memory("", [])


async def test_append_then_load_roundtrips(fake_mem):
    await sm.append_turns("s1", "hi", "hello there")
    mem = await sm.load_memory("s1")
    assert mem.summary == ""
    assert mem.turns == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello there"},
    ]


async def test_hard_cap_without_summarizer(fake_mem):
    # No summarize callback: oldest messages drop at the hard cap.
    for i in range(sm._HARD_CAP):  # each call appends 2 messages
        await sm.append_turns("s1", f"q{i}", f"a{i}")
    turns = (await sm.load_memory("s1")).turns
    assert len(turns) == sm._HARD_CAP
    assert turns[-1] == {"role": "assistant", "content": f"a{sm._HARD_CAP - 1}"}


async def test_summarization_folds_overflow(fake_mem, monkeypatch):
    # Tiny budget so the conversation exceeds it quickly.
    monkeypatch.setattr(sm, "get_settings", lambda: _settings(5))
    seen = []

    async def fake_summarize(prev, overflow):
        seen.append((prev, [t["content"] for t in overflow]))
        return f"SUMMARY[{len(overflow)}]"

    # Three exchanges -> 6 messages -> exceeds budget and len > _KEEP_RECENT.
    for i in range(3):
        await sm.append_turns(
            "s1", f"question number {i}", f"answer number {i}",
            summarize=fake_summarize,
        )

    mem = await sm.load_memory("s1")
    assert mem.summary.startswith("SUMMARY")
    assert len(mem.turns) == sm._KEEP_RECENT  # only the most recent kept verbatim
    assert seen  # the summarizer was invoked with the overflow


async def test_append_is_noop_without_session_id(fake_mem):
    await sm.append_turns(None, "q", "a")
    assert fake_mem.kv == {}
