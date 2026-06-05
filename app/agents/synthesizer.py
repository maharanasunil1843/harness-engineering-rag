"""Multi-source answer synthesis with citations and confidence scoring."""
import re
import time
from collections.abc import AsyncIterator
from typing import Any

from anthropic import AsyncAnthropic
from pydantic import BaseModel

from app.config import get_settings
from app.observability.tracing import track_token_usage
from app.retrieval.hybrid import RetrievedChunk
from app.sql.agent import SQLResult

_SYSTEM = """\
You are an expert on harness engineering for AI agents. Synthesize a precise, technical answer from the provided sources.

Rules:
- Cite sources inline as [Source N]. Every factual claim must have a citation.
- If sources contain conflicting information, acknowledge the disagreement and explain both positions.
- If sources don't contain enough information, say so honestly — never fabricate.
- If a "Conversation so far" is provided, use it for continuity (the question may build on earlier turns), but ground every factual claim in the Sources, not the conversation.
- For hybrid queries (both retrieval and SQL results), weave both into a coherent answer.
- End with a confidence self-assessment: a float 0.0-1.0 on the very last line, formatted as: Confidence: <float>\
"""


class SynthesizedAnswer(BaseModel):
    answer: str
    sources: list[dict]
    confidence: float
    trace_id: str
    latency_ms: float
    # Set by the supervisor from the graph state; the synthesizer itself
    # always produces a fresh (non-cached) answer.
    cache_hit: bool = False


def _format_retrieval(chunks: list[RetrievedChunk]) -> str:
    parts = []
    for i, c in enumerate(chunks, start=1):
        doc_title = c.metadata.get("title", c.doc_id)
        parts.append(
            f'[Source {i}] (doc: "{doc_title}", type: {c.element_type}, score: {c.score:.3f}):\n{c.content}'
        )
    return "\n\n".join(parts)


def _format_sql(result: SQLResult, offset: int) -> str:
    rows_preview = result.rows[:10]
    formatted = "\n".join(str(r) for r in rows_preview)
    return (
        f"[Source {offset}] [SQL Result]\n"
        f"Query: {result.sql}\n"
        f"Rows ({len(result.rows)} total, showing first 10):\n{formatted}\n"
        f"Explanation: {result.explanation}"
    )


def _parse_confidence(text: str) -> float:
    # Look for "Confidence: <float>" on any line, prefer the last occurrence
    matches = re.findall(r"[Cc]onfidence:\s*([0-9]*\.?[0-9]+)", text)
    if matches:
        try:
            return min(1.0, max(0.0, float(matches[-1])))
        except ValueError:
            pass
    return 0.5


def _build_request(
    query: str,
    retrieval_results: list[RetrievedChunk] | None,
    sql_result: SQLResult | None,
    history: list[dict] | None,
    summary: str | None,
) -> tuple[str, list[dict]]:
    """Build the synthesizer user message and the structured `sources` list."""
    source_blocks: list[str] = []
    sources: list[dict] = []

    if retrieval_results:
        source_blocks.append(_format_retrieval(retrieval_results))
        for c in retrieval_results:
            sources.append(
                {
                    "chunk_id": c.chunk_id,
                    "doc_id": c.doc_id,
                    "doc_title": c.metadata.get("title", c.doc_id),
                    "element_type": c.element_type,
                    "score": c.score,
                    "source_type": "retrieval",
                    "content": c.content,
                }
            )

    if sql_result:
        offset = len(retrieval_results or []) + 1
        source_blocks.append(_format_sql(sql_result, offset))
        sources.append(
            {
                "source_type": "sql",
                "query": sql_result.sql,
                "row_count": len(sql_result.rows),
                "rows": sql_result.rows[:20],
                "explanation": sql_result.explanation,
            }
        )

    if not source_blocks:
        source_blocks.append("No sources available. Answer from general knowledge only.")

    convo_parts = []
    if summary:
        convo_parts.append(f"Summary of earlier conversation:\n{summary}")
    if history:
        lines = [
            f"{t.get('role', 'user')}: {(t.get('content') or '')[:500]}"
            for t in history[-6:]
        ]
        convo_parts.append("Recent turns:\n" + "\n".join(lines))
    convo = "\n\n".join(convo_parts) + "\n\n" if convo_parts else ""

    user_content = (
        convo
        + f"Question: {query}\n\n"
        + "Sources:\n\n"
        + "\n\n---\n\n".join(source_blocks)
    )
    return user_content, sources


# The trailing "Confidence: X" line is parsed into the confidence field — strip
# it from the displayed/streamed/cached text. HOLDBACK chars at the tail are
# buffered until the stream ends so a forming "Confidence:" marker never leaks.
_CONFIDENCE_RE = re.compile(r"\s*Confidence:\s*[0-9]*\.?[0-9]+\s*$")
_HOLDBACK = 32


async def synthesize_stream(
    query: str,
    retrieval_results: list[RetrievedChunk] | None,
    sql_result: SQLResult | None,
    trace_id: str = "",
    history: list[dict] | None = None,
    summary: str | None = None,
) -> AsyncIterator[tuple[str, Any]]:
    """Stream the answer token-by-token.

    Yields ("token", text) as the model generates, then ("done",
    SynthesizedAnswer). The trailing Confidence line is held back and stripped,
    so it never reaches the client and the stored answer is clean.
    """
    t0 = time.perf_counter()
    s = get_settings()
    client = AsyncAnthropic(api_key=s.anthropic_api_key)
    user_content, sources = _build_request(
        query, retrieval_results, sql_result, history, summary
    )

    full = ""
    emitted = 0
    async with client.messages.stream(
        model=s.synthesizer_model,
        max_tokens=2048,
        system=[{"type": "text", "text": _SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_content}],
    ) as stream:
        async for text in stream.text_stream:
            full += text
            safe_upto = len(full) - _HOLDBACK
            if safe_upto > emitted:
                yield ("token", full[emitted:safe_upto])
                emitted = safe_upto
        final_msg = await stream.get_final_message()

    track_token_usage(
        s.synthesizer_model,
        final_msg.usage.input_tokens,
        final_msg.usage.output_tokens,
        cost=0.0,
    )

    confidence = _parse_confidence(full)
    answer_text = _CONFIDENCE_RE.sub("", full).rstrip()
    # Emit whatever clean tail wasn't flushed during streaming.
    if emitted < len(answer_text):
        yield ("token", answer_text[emitted:])

    yield (
        "done",
        SynthesizedAnswer(
            answer=answer_text,
            sources=sources,
            confidence=confidence,
            trace_id=trace_id,
            latency_ms=(time.perf_counter() - t0) * 1000,
        ),
    )


async def synthesize(
    query: str,
    retrieval_results: list[RetrievedChunk] | None,
    sql_result: SQLResult | None,
    trace_id: str = "",
    history: list[dict] | None = None,
    summary: str | None = None,
) -> SynthesizedAnswer:
    """Non-streaming wrapper: drain synthesize_stream and return the answer."""
    answer: SynthesizedAnswer | None = None
    async for kind, val in synthesize_stream(
        query, retrieval_results, sql_result, trace_id, history, summary
    ):
        if kind == "done":
            answer = val
    assert answer is not None  # synthesize_stream always yields a final ("done", ...)
    return answer
