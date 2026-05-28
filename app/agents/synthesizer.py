"""Multi-source answer synthesis with citations and confidence scoring."""
import re
import time

from anthropic import Anthropic
from pydantic import BaseModel

from app.config import get_settings
from app.observability.tracing import traced, track_token_usage
from app.retrieval.hybrid import RetrievedChunk
from app.sql.agent import SQLResult

_SYSTEM = """\
You are an expert on harness engineering for AI agents. Synthesize a precise, technical answer from the provided sources.

Rules:
- Cite sources inline as [Source N]. Every factual claim must have a citation.
- If sources contain conflicting information, acknowledge the disagreement and explain both positions.
- If sources don't contain enough information, say so honestly — never fabricate.
- For hybrid queries (both retrieval and SQL results), weave both into a coherent answer.
- End with a confidence self-assessment: a float 0.0-1.0 on the very last line, formatted as: Confidence: <float>\
"""


class SynthesizedAnswer(BaseModel):
    answer: str
    sources: list[dict]
    confidence: float
    trace_id: str
    latency_ms: float


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


@traced("synthesizer")
async def synthesize(
    query: str,
    retrieval_results: list[RetrievedChunk] | None,
    sql_result: SQLResult | None,
    trace_id: str = "",
) -> SynthesizedAnswer:
    t0 = time.perf_counter()
    s = get_settings()
    client = Anthropic(api_key=s.anthropic_api_key)

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
            }
        )

    if not source_blocks:
        source_blocks.append("No sources available. Answer from general knowledge only.")

    user_content = (
        f"Question: {query}\n\n"
        "Sources:\n\n"
        + "\n\n---\n\n".join(source_blocks)
    )

    resp = client.messages.create(
        model=s.synthesizer_model,
        max_tokens=2048,
        system=[{"type": "text", "text": _SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_content}],
    )

    track_token_usage(
        s.synthesizer_model,
        resp.usage.input_tokens,
        resp.usage.output_tokens,
        cost=0.0,
    )

    answer_text = resp.content[0].text
    confidence = _parse_confidence(answer_text)
    latency_ms = (time.perf_counter() - t0) * 1000

    return SynthesizedAnswer(
        answer=answer_text,
        sources=sources,
        confidence=confidence,
        trace_id=trace_id,
        latency_ms=latency_ms,
    )
