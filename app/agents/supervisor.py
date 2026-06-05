"""LangGraph supervisor orchestrating the full agentic RAG pipeline.

Conversational flow: classify FIRST (the rewriter resolves follow-ups against
the session history into a STANDALONE query), then embed + cache-check on that
standalone query, then retrieve/synthesize, then persist the turn. Keying the
cache on the standalone query keeps follow-ups correct (a raw "what about it?"
is context-dependent and must not be served by exact text).
"""
import asyncio
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

from langgraph.config import get_stream_writer
from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from app.agents.conversation_summary import summarize_conversation
from app.agents.query_rewriter import ClassifiedQuery, rewrite_and_classify
from app.agents.synthesizer import SynthesizedAnswer, synthesize_stream
from app.config import get_settings
from app.retrieval.cache import cache_get, cache_set
from app.retrieval.cache_verify import verify_cache_match
from app.retrieval.hybrid import RetrievedChunk, hybrid_retrieve, _embed_query
from app.retrieval.rate_limiter import check_rate_limit
from app.retrieval.session_memory import append_turns, load_memory
from app.sql.agent import SQLResult, text_to_sql


class AgentState(TypedDict):
    query: str
    session_id: str | None
    history: list[dict]
    summary: str
    standalone_query: str
    query_embedding: list[float]
    classified: ClassifiedQuery | None
    retrieval_results: list[RetrievedChunk]
    sql_result: SQLResult | None
    answer: SynthesizedAnswer | None
    trace_id: str
    cache_hit: bool
    error: str | None


def _standalone(state: AgentState) -> str:
    classified = state.get("classified")
    return classified.rewritten if classified else state["query"]


# ── Node implementations ────────────────────────────────────────────────────

async def _node_classify(state: AgentState) -> dict[str, Any]:
    try:
        classified = await rewrite_and_classify(
            state["query"], state.get("history"), state.get("summary")
        )
        return {"classified": classified, "standalone_query": classified.rewritten}
    except Exception as e:
        return {"error": f"classify failed: {e}"}


async def _node_embed(state: AgentState) -> dict[str, Any]:
    # Embed the STANDALONE query (resolved follow-up), not the raw text.
    return {"query_embedding": await _embed_query(_standalone(state))}


async def _node_cache_check(state: AgentState) -> dict[str, Any]:
    # Banded semantic match on the standalone query: trust high-similarity hits,
    # verify gray-zone candidates with a cheap LLM check, miss below the floor.
    s = get_settings()
    try:
        hit = await cache_get(
            _standalone(state),
            state["query_embedding"],
            verify=verify_cache_match,
            trust_threshold=s.cache_trust_threshold,
            floor_threshold=s.cache_floor_threshold,
        )
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


async def _node_retrieval(state: AgentState) -> dict[str, Any]:
    try:
        chunks = await hybrid_retrieve(
            _standalone(state),
            top_k=10,
            query_embedding=state.get("query_embedding"),
        )
        return {"retrieval_results": chunks}
    except Exception as e:
        return {"error": f"retrieval failed: {e}", "retrieval_results": []}


async def _node_sql(state: AgentState) -> dict[str, Any]:
    try:
        result = await text_to_sql(_standalone(state))
        return {"sql_result": result}
    except Exception as e:
        return {"error": f"sql failed: {e}", "sql_result": None}


async def _node_hybrid_workers(state: AgentState) -> dict[str, Any]:
    query = _standalone(state)
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
    # Stream tokens out via the custom stream channel as they're generated;
    # get_stream_writer() is a no-op under ainvoke (the /query path). Answer the
    # user's literal question, with the conversation for context.
    writer = get_stream_writer()
    answer: SynthesizedAnswer | None = None
    try:
        async for kind, val in synthesize_stream(
            query=state["query"],
            retrieval_results=state.get("retrieval_results") or None,
            sql_result=state.get("sql_result"),
            trace_id=state["trace_id"],
            history=state.get("history"),
            summary=state.get("summary"),
        ):
            if kind == "token":
                writer({"token": val})
            else:
                answer = val
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
        # Key on the standalone query. Alias the raw query ONLY on a first turn
        # (no history) — a follow-up's raw text is context-dependent and must
        # not become an exact-match key.
        aliases = [] if state.get("history") else [state["query"]]
        try:
            await cache_set(
                _standalone(state),
                state["query_embedding"],
                answer.answer,
                answer.sources,
                answer.confidence,
                alias_queries=aliases,
            )
        except Exception:
            pass  # Cache write failure is non-fatal
    return {}


async def _node_append_memory(state: AgentState) -> dict[str, Any]:
    answer = state.get("answer")
    if state.get("session_id") and answer:
        try:
            await append_turns(
                state["session_id"],
                state["query"],
                answer.answer,
                summarize=summarize_conversation,
            )
        except Exception:
            pass  # Memory write failure is non-fatal
    return {}


# ── Routing functions ────────────────────────────────────────────────────────

def _route_after_cache(state: AgentState) -> str:
    if state.get("cache_hit"):
        return "cache_store"
    return "rate_limit"


def _route_after_rate_limit(state: AgentState) -> str:
    if state.get("answer"):  # rate limit fired
        return "cache_store"
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

    g.add_node("classify", _node_classify)
    g.add_node("embed", _node_embed)
    g.add_node("cache_check", _node_cache_check)
    g.add_node("rate_limit", _node_rate_limit)
    g.add_node("retrieval", _node_retrieval)
    g.add_node("sql", _node_sql)
    g.add_node("hybrid", _node_hybrid_workers)
    g.add_node("synthesize", _node_synthesize)
    g.add_node("cache_store", _node_cache_store)
    g.add_node("append_memory", _node_append_memory)

    # classify (resolve follow-up) → embed standalone → cache-check standalone.
    g.set_entry_point("classify")
    g.add_edge("classify", "embed")
    g.add_edge("embed", "cache_check")

    g.add_conditional_edges(
        "cache_check",
        _route_after_cache,
        {"cache_store": "cache_store", "rate_limit": "rate_limit"},
    )
    g.add_conditional_edges(
        "rate_limit",
        _route_after_rate_limit,
        {
            "cache_store": "cache_store",
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
    g.add_edge("cache_store", "append_memory")
    g.add_edge("append_memory", END)

    return g.compile()


_graph = _build_graph()


def _initial_state(
    query: str, session_id: str | None, history: list[dict], summary: str
) -> AgentState:
    return {
        "query": query,
        "session_id": session_id,
        "history": history,
        "summary": summary,
        "standalone_query": "",
        "query_embedding": [],
        "classified": None,
        "retrieval_results": [],
        "sql_result": None,
        "answer": None,
        "trace_id": str(uuid4()),
        "cache_hit": False,
        "error": None,
    }


async def ask(
    query: str,
    *,
    session_id: str | None = None,
    history: list[dict] | None = None,
    summary: str | None = None,
) -> SynthesizedAnswer:
    """Public API: run the full agentic RAG pipeline for a query."""
    if history is None or summary is None:
        mem = await load_memory(session_id)
        history = mem.turns if history is None else history
        summary = mem.summary if summary is None else summary
    state = _initial_state(query, session_id, history, summary)
    final_state = await _graph.ainvoke(state)
    answer = final_state.get("answer")
    if answer is None:
        answer = SynthesizedAnswer(
            answer="No answer produced.",
            sources=[],
            confidence=0.0,
            trace_id=state["trace_id"],
            latency_ms=0.0,
        )
    answer.cache_hit = bool(final_state.get("cache_hit", False))
    return answer


async def ask_stream(
    query: str,
    *,
    session_id: str | None = None,
    history: list[dict] | None = None,
    summary: str | None = None,
) -> AsyncIterator[tuple[str, Any]]:
    """Run the pipeline ONCE, streaming events as graph nodes complete.

    Event kinds: ("intent", str) · ("status", {"step": ...}) ·
    ("sources", list[RetrievedChunk]) · ("answer", SynthesizedAnswer).
    """
    if history is None or summary is None:
        mem = await load_memory(session_id)
        history = mem.turns if history is None else history
        summary = mem.summary if summary is None else summary
    state = _initial_state(query, session_id, history, summary)

    final_answer: SynthesizedAnswer | None = None
    cache_hit = False
    local_intent: str | None = None

    # "updates" yields {node: state_delta} after each node; "custom" yields the
    # tokens the synthesize node emits live. With a list of modes astream yields
    # (mode, data) tuples.
    async for mode, data in _graph.astream(state, stream_mode=["updates", "custom"]):
        if mode == "custom":
            tok = data.get("token") if isinstance(data, dict) else None
            if tok:
                yield ("token", tok)
            continue

        for node, delta in data.items():
            if not isinstance(delta, dict):
                continue

            if delta.get("cache_hit"):
                cache_hit = True

            if node == "classify":
                classified = delta.get("classified")
                if classified is not None:
                    local_intent = classified.intent
                    yield ("intent", local_intent)
            elif node == "cache_check":
                # Announce the next step only if we didn't just cache-hit.
                if not delta.get("cache_hit") and local_intent is not None:
                    if local_intent == "sql":
                        yield ("status", {"step": "querying_sql"})
                    elif local_intent in ("retrieval", "hybrid"):
                        yield ("status", {"step": "retrieving",
                                          "intent": local_intent})
                    else:  # direct — straight to synthesis
                        yield ("status", {"step": "synthesizing"})
            elif node in ("retrieval", "hybrid"):
                chunks = delta.get("retrieval_results") or []
                if chunks:
                    yield ("sources", chunks)
                yield ("status", {"step": "synthesizing"})
            elif node == "sql":
                yield ("status", {"step": "synthesizing"})

            if delta.get("answer") is not None:
                final_answer = delta["answer"]

    if final_answer is None:
        final_answer = SynthesizedAnswer(
            answer="No answer produced.",
            sources=[],
            confidence=0.0,
            trace_id=state["trace_id"],
            latency_ms=0.0,
        )
    final_answer.cache_hit = cache_hit
    yield ("answer", final_answer)
