"""LangGraph supervisor orchestrating the full agentic RAG pipeline."""
import asyncio
from typing import Any
from uuid import uuid4

from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from app.agents.query_rewriter import ClassifiedQuery, rewrite_and_classify
from app.agents.synthesizer import SynthesizedAnswer, synthesize
from app.retrieval.cache import cache_get, cache_set
from app.retrieval.hybrid import RetrievedChunk, hybrid_retrieve, _embed_query
from app.retrieval.rate_limiter import check_rate_limit
from app.sql.agent import SQLResult, text_to_sql


class AgentState(TypedDict):
    query: str
    query_embedding: list[float]
    classified: ClassifiedQuery | None
    retrieval_results: list[RetrievedChunk]
    sql_result: SQLResult | None
    answer: SynthesizedAnswer | None
    trace_id: str
    cache_hit: bool
    error: str | None


# ── Node implementations ────────────────────────────────────────────────────

async def _node_embed(state: AgentState) -> dict[str, Any]:
    embedding = _embed_query(state["query"])
    return {"query_embedding": embedding}


async def _node_cache_check(state: AgentState) -> dict[str, Any]:
    try:
        hit = await cache_get(state["query"], state["query_embedding"])
        if hit:
            answer = SynthesizedAnswer(
                answer=hit.answer,
                sources=hit.sources,
                confidence=hit.confidence,
                trace_id=state["trace_id"],
                latency_ms=0.0,
            )
            return {"answer": answer, "cache_hit": True}
    except Exception as e:
        return {"error": f"cache_check failed: {e}", "cache_hit": False}
    return {"cache_hit": False}


async def _node_rate_limit(state: AgentState) -> dict[str, Any]:
    try:
        result = await check_rate_limit()
        if not result.allowed:
            answer = SynthesizedAnswer(
                answer=f"Rate limit exceeded. Try again in {result.reset_in:.1f}s.",
                sources=[],
                confidence=1.0,
                trace_id=state["trace_id"],
                latency_ms=0.0,
            )
            return {"answer": answer}
    except Exception as e:
        return {"error": f"rate_limit failed: {e}"}
    return {}


async def _node_classify(state: AgentState) -> dict[str, Any]:
    try:
        classified = await rewrite_and_classify(state["query"])
        return {"classified": classified}
    except Exception as e:
        return {"error": f"classify failed: {e}"}


async def _node_retrieval(state: AgentState) -> dict[str, Any]:
    classified = state.get("classified")
    query = classified.rewritten if classified else state["query"]
    try:
        chunks = await hybrid_retrieve(
            query,
            top_k=10,
            query_embedding=state.get("query_embedding"),
        )
        return {"retrieval_results": chunks}
    except Exception as e:
        return {"error": f"retrieval failed: {e}", "retrieval_results": []}


async def _node_sql(state: AgentState) -> dict[str, Any]:
    classified = state.get("classified")
    question = classified.rewritten if classified else state["query"]
    try:
        result = await text_to_sql(question)
        return {"sql_result": result}
    except Exception as e:
        return {"error": f"sql failed: {e}", "sql_result": None}


async def _node_hybrid_workers(state: AgentState) -> dict[str, Any]:
    classified = state.get("classified")
    query = classified.rewritten if classified else state["query"]
    embedding = state.get("query_embedding")

    retrieval_task = hybrid_retrieve(query, top_k=10, query_embedding=embedding)
    sql_task = text_to_sql(query)

    results = await asyncio.gather(retrieval_task, sql_task, return_exceptions=True)

    out: dict[str, Any] = {}
    if isinstance(results[0], Exception):
        out["error"] = f"retrieval failed: {results[0]}"
        out["retrieval_results"] = []
    else:
        out["retrieval_results"] = results[0]

    if isinstance(results[1], Exception):
        err = out.get("error", "")
        out["error"] = (err + f" sql failed: {results[1]}").strip()
        out["sql_result"] = None
    else:
        out["sql_result"] = results[1]

    return out


async def _node_synthesize(state: AgentState) -> dict[str, Any]:
    try:
        answer = await synthesize(
            query=state["query"],
            retrieval_results=state.get("retrieval_results") or None,
            sql_result=state.get("sql_result"),
            trace_id=state["trace_id"],
        )
        return {"answer": answer}
    except Exception as e:
        return {
            "answer": SynthesizedAnswer(
                answer=f"Synthesis failed: {e}",
                sources=[],
                confidence=0.0,
                trace_id=state["trace_id"],
                latency_ms=0.0,
            )
        }


async def _node_cache_store(state: AgentState) -> dict[str, Any]:
    answer = state.get("answer")
    if answer and not state.get("cache_hit"):
        try:
            await cache_set(
                state["query"],
                state["query_embedding"],
                answer.answer,
                answer.sources,
                answer.confidence,
            )
        except Exception:
            pass  # Cache write failure is non-fatal
    return {}


# ── Routing functions ────────────────────────────────────────────────────────

def _route_after_cache(state: AgentState) -> str:
    if state.get("cache_hit"):
        return "done"
    return "rate_limit"


def _route_after_rate_limit(state: AgentState) -> str:
    # If answer is already set, rate limit fired
    if state.get("answer"):
        return "done"
    return "classify"


def _route_after_classify(state: AgentState) -> str:
    classified = state.get("classified")
    if not classified:
        return "retrieval"  # fallback
    intent = classified.intent
    if intent == "sql":
        return "sql"
    if intent == "hybrid":
        return "hybrid"
    if intent == "direct":
        return "synthesize"
    return "retrieval"


# ── Graph assembly ────────────────────────────────────────────────────────────

def _build_graph() -> Any:
    g: StateGraph = StateGraph(AgentState)

    g.add_node("embed", _node_embed)
    g.add_node("cache_check", _node_cache_check)
    g.add_node("rate_limit", _node_rate_limit)
    g.add_node("classify", _node_classify)
    g.add_node("retrieval", _node_retrieval)
    g.add_node("sql", _node_sql)
    g.add_node("hybrid", _node_hybrid_workers)
    g.add_node("synthesize", _node_synthesize)
    g.add_node("cache_store", _node_cache_store)

    g.set_entry_point("embed")
    g.add_edge("embed", "cache_check")

    g.add_conditional_edges(
        "cache_check",
        _route_after_cache,
        {"done": "cache_store", "rate_limit": "rate_limit"},
    )
    g.add_conditional_edges(
        "rate_limit",
        _route_after_rate_limit,
        {"done": "cache_store", "classify": "classify"},
    )
    g.add_conditional_edges(
        "classify",
        _route_after_classify,
        {
            "retrieval": "retrieval",
            "sql": "sql",
            "hybrid": "hybrid",
            "synthesize": "synthesize",
        },
    )

    g.add_edge("retrieval", "synthesize")
    g.add_edge("sql", "synthesize")
    g.add_edge("hybrid", "synthesize")
    g.add_edge("synthesize", "cache_store")
    g.add_edge("cache_store", END)

    return g.compile()


_graph = _build_graph()


async def ask(query: str) -> SynthesizedAnswer:
    """Public API: run the full agentic RAG pipeline for a query."""
    trace_id = str(uuid4())
    initial_state: AgentState = {
        "query": query,
        "query_embedding": [],
        "classified": None,
        "retrieval_results": [],
        "sql_result": None,
        "answer": None,
        "trace_id": trace_id,
        "cache_hit": False,
        "error": None,
    }
    final_state = await _graph.ainvoke(initial_state)
    answer = final_state.get("answer")
    if answer is None:
        answer = SynthesizedAnswer(
            answer="No answer produced.",
            sources=[],
            confidence=0.0,
            trace_id=trace_id,
            latency_ms=0.0,
        )
    return answer
