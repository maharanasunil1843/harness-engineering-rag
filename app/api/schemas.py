"""API request/response schemas."""
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Prompt-injection patterns we reject outright. Case-insensitive, substring match.
# This is a first-line cheap filter — the synthesizer system prompt is the
# real defense. Anything that hits one of these is almost always abuse.
_INJECTION_PATTERNS = (
    "ignore previous instructions",
    "ignore all previous instructions",
    "ignore the above",
    "disregard previous instructions",
    "disregard the above",
    "forget previous instructions",
    "system:",
    "assistant:",
    "<|im_start|>",
    "<|im_end|>",
    "you are now",
    "new instructions:",
    "override your instructions",
)


def _looks_like_injection(text: str) -> bool:
    t = text.lower()
    return any(p in t for p in _INJECTION_PATTERNS)


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    session_id: str | None = None
    metadata_filter: dict | None = None

    @field_validator("query")
    @classmethod
    def _strip_and_check(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("query cannot be empty or whitespace-only")
        if _looks_like_injection(stripped):
            raise ValueError("query rejected: prompt-injection pattern detected")
        # Collapse any null bytes that might confuse downstream tooling.
        return re.sub(r"\x00", "", stripped)


class SourceInfo(BaseModel):
    chunk_id: str | None = None
    doc_id: str | None = None
    doc_title: str | None = None
    element_type: str | None = None
    score: float | None = None
    source_type: str = "retrieval"


class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceInfo]
    confidence: float
    trace_id: str
    latency_ms: float
    cache_hit: bool = False
    intent: str | None = None


class StreamEvent(BaseModel):
    event: Literal["status", "source", "token", "done", "error"]
    data: str | dict


class HealthResponse(BaseModel):
    status: str = "healthy"
    version: str = "0.1.0"
    db_connected: bool
    cache_connected: bool
    cache_stats: dict | None = None
    tracing_healthy: bool = True
    query_count: int = 0
    cache_hit_rate: float = 0.0
