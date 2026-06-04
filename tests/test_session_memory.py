"""Session memory load/append against an in-memory fake Redis."""
import pytest

from app.retrieval import session_memory as sm


class FakeRedis:
    def __init__(self) -> None:
        self.kv: dict[str, str] = {}

    def get(self, k):
        return self.kv.get(k)

    def set(self, k, v, ex=None, **kw):
        self.kv[k] = v

    def expire(self, k, seconds, **kw):
        return True


@pytest.fixture
def fake_mem(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(sm, "_redis", lambda: fake)
    return fake


async def test_load_empty_session_returns_empty(fake_mem):
    assert await sm.load_history("s1") == []
    assert await sm.load_history(None) == []


async def test_append_then_load_roundtrips(fake_mem):
    await sm.append_turns("s1", "hi", "hello there")
    assert await sm.load_history("s1") == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello there"},
    ]


async def test_history_capped_to_max_turns(fake_mem):
    for i in range(sm._MAX_TURNS):  # each call appends 2 messages
        await sm.append_turns("s1", f"q{i}", f"a{i}")
    hist = await sm.load_history("s1")
    assert len(hist) == sm._MAX_TURNS  # capped at the most recent N messages
    assert hist[-1] == {"role": "assistant", "content": f"a{sm._MAX_TURNS - 1}"}


async def test_append_is_noop_without_session_id(fake_mem):
    await sm.append_turns(None, "q", "a")
    assert fake_mem.kv == {}
