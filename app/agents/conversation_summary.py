"""Rolling conversation summary (Haiku) for long sessions.

When the verbatim recent turns exceed the memory budget, the oldest are folded
into a running summary so the pipeline keeps long-conversation context without
resending the whole transcript. Injected into session_memory.append_turns as a
callback so the memory layer stays LLM-free.
"""
from anthropic import AsyncAnthropic

from app.config import get_settings
from app.observability.tracing import track_token_usage

_SYSTEM = (
    "You maintain a running summary of an ongoing conversation between a user and "
    "an assistant about agent-harness engineering. Given the PREVIOUS SUMMARY and "
    "the NEW EXCHANGES being archived, produce an updated summary that preserves "
    "the topics discussed, key facts established, and any user goals or "
    "preferences. Be concise — a few sentences to a short paragraph. Output only "
    "the summary text."
)


async def summarize_conversation(
    existing_summary: str, overflow_turns: list[dict]
) -> str:
    """Fold `overflow_turns` into `existing_summary`, returning the new summary."""
    s = get_settings()
    client = AsyncAnthropic(api_key=s.anthropic_api_key)
    convo = "\n".join(
        f"{t.get('role', 'user')}: {(t.get('content') or '')[:800]}"
        for t in overflow_turns
    )
    prev = existing_summary or "(none yet)"
    resp = await client.messages.create(
        model=s.worker_model,
        max_tokens=400,
        system=[
            {"type": "text", "text": _SYSTEM, "cache_control": {"type": "ephemeral"}}
        ],
        messages=[
            {
                "role": "user",
                "content": f"PREVIOUS SUMMARY:\n{prev}\n\nNEW EXCHANGES:\n{convo}",
            }
        ],
    )
    track_token_usage(
        s.worker_model, resp.usage.input_tokens, resp.usage.output_tokens, cost=0.0
    )
    return "".join(b.text for b in resp.content if b.type == "text").strip()
