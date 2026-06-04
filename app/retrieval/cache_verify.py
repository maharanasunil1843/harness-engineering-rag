"""Cheap LLM guardrail for the semantic cache.

When a new query matches a cached entry only in the gray similarity band (high
enough to be a likely rephrasing, not high enough to trust blindly), this asks a
small/fast model whether the cached answer actually addresses the new question.
It lets the cache accept genuine rephrasings without serving an answer to a
different-but-lexically-similar question. Kept separate from cache.py so the
cache layer stays free of LLM dependencies (it takes this as a callback).
"""
from anthropic import AsyncAnthropic

from app.config import get_settings
from app.observability.tracing import track_token_usage

_SYSTEM = (
    "You judge whether a previously generated ANSWER fully addresses a NEW "
    "QUESTION. Reply with exactly one word: YES if the answer directly and "
    "completely answers the new question, or NO if it is about a different "
    "topic or fails to answer it. Output only YES or NO."
)


async def verify_cache_match(question: str, answer: str) -> bool:
    """Return True if `answer` is a valid response to `question`."""
    s = get_settings()
    client = AsyncAnthropic(api_key=s.anthropic_api_key)
    # Truncate the answer — the lead is enough to judge topical match, and it
    # keeps the check cheap and fast.
    snippet = answer[:1200]
    resp = await client.messages.create(
        model=s.worker_model,
        max_tokens=4,
        system=[
            {"type": "text", "text": _SYSTEM, "cache_control": {"type": "ephemeral"}}
        ],
        messages=[
            {
                "role": "user",
                "content": f"NEW QUESTION:\n{question}\n\nANSWER:\n{snippet}",
            }
        ],
    )
    track_token_usage(
        s.worker_model, resp.usage.input_tokens, resp.usage.output_tokens, cost=0.0
    )
    text = "".join(b.text for b in resp.content if b.type == "text").strip().lower()
    return text.startswith("y")
