"""API request/response schemas."""
from typing import Literal

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    session_id: str | None = None
    metadata_filter: dict | None = None


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
