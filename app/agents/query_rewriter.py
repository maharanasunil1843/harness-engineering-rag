"""Query rewriting and intent classification — the planner/router node."""
from typing import Literal

from anthropic import Anthropic
from pydantic import BaseModel

from app.config import get_settings
from app.observability.tracing import traced, track_token_usage

_CLASSIFY_TOOL = {
    "name": "classify_query",
    "description": "Classify the user query and rewrite it for optimal retrieval.",
    "input_schema": {
        "type": "object",
        "properties": {
            "intent": {
                "type": "string",
                "enum": ["retrieval", "sql", "hybrid", "direct"],
                "description": "Routing intent for the query.",
            },
            "rewritten": {
                "type": "string",
                "description": "Rewritten query optimized for retrieval or SQL generation.",
            },
            "reasoning": {
                "type": "string",
                "description": "One-sentence explanation of why this intent was chosen.",
            },
        },
        "required": ["intent", "rewritten", "reasoning"],
    },
}

_SYSTEM = """\
You are a query router for a knowledge base about harness engineering for AI agents.

The knowledge base contains:
1. Document corpus (articles by Osmani, Anthropic, HumanLayer, Viv Trivedy, Red Hat, and a practitioner case study from Sugna Metals) — use "retrieval" for conceptual questions.
2. Structured catalog tables: harness_components (108 named components with categories), failure_modes (43 named failures), practitioners (7 people), harnesses (14 products), benchmark_results (9 entries) — use "sql" for enumeration, filtering, counting, or comparison queries.
3. Both — use "hybrid" when the answer needs document prose AND structured data joined.
4. Neither — use "direct" for greetings or out-of-scope questions.

Rewrite the query for optimal retrieval: expand abbreviations, resolve pronouns, add domain context.\
"""


class ClassifiedQuery(BaseModel):
    original: str
    rewritten: str
    intent: Literal["retrieval", "sql", "hybrid", "direct"]
    reasoning: str


@traced("query_rewriter")
async def rewrite_and_classify(query: str) -> ClassifiedQuery:
    s = get_settings()
    client = Anthropic(api_key=s.anthropic_api_key)

    resp = client.messages.create(
        model=s.planner_model,
        max_tokens=512,
        system=[{"type": "text", "text": _SYSTEM, "cache_control": {"type": "ephemeral"}}],
        tools=[_CLASSIFY_TOOL],
        tool_choice={"type": "tool", "name": "classify_query"},
        messages=[{"role": "user", "content": query}],
    )

    track_token_usage(
        s.planner_model,
        resp.usage.input_tokens,
        resp.usage.output_tokens,
        cost=0.0,
    )

    tool_input: dict = {}
    for block in resp.content:
        if block.type == "tool_use" and block.name == "classify_query":
            tool_input = block.input
            break

    return ClassifiedQuery(
        original=query,
        rewritten=tool_input.get("rewritten", query),
        intent=tool_input.get("intent", "retrieval"),
        reasoning=tool_input.get("reasoning", ""),
    )
