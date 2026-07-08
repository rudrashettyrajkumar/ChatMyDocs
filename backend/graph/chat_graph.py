"""The chat turn as a LangGraph StateGraph (v3 BYOK architecture).

    guardrail ─┬─▶ context ─┬─▶ rewrite ─┬─▶ retrieve ─▶ rerank ─▶ END
               │            │            └─(route=direct)─▶ END
               └─(blocked)──┴─(no docs)──▶ END

Pipeline order is still LAW (ARCHITECTURE §3.2) — the graph just makes it
explicit and gives every request-scoped model decision one carrier: the
`RunConfig` in state. Nodes are PLAIN async functions returning partial state
updates, which buys two things: they unit-test without langgraph installed,
and `prepare()` can fall back to running them sequentially when the langgraph
import fails (errors degrade, never break — a missing optional dep must not
take chat down).

Answer streaming intentionally stays OUTSIDE the graph, in chat_pipeline:
token-level SSE plumbed through graph event streams adds fragility with zero
user benefit; the graph's job ends when the state holds everything the
answerer needs.

The input guardrail node runs FIRST and short-circuits to END — blocked
messages reach zero LLM calls and zero retrieval (invariant #1).
"""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from backend.agents.retrieval_agent import RetrievedChunk, retrieve
from backend.agents.rewrite_agent import rewrite
from backend.llm import reranker
from backend.llm.runconfig import DEFAULT, RunConfig
from backend.services import embed_signature
from backend.utils.config import get_settings
from backend.utils.guardrails import check_input, deflection
from backend.utils.prompt_assembly import no_docs_message

_log = logging.getLogger("docchat.chat_graph")


class ChatState(TypedDict, total=False):
    # Inputs (set once by chat_pipeline)
    question: str
    session_id: str
    history: list[dict[str, str]]
    filenames: list[str]
    cfg: RunConfig
    # Outputs (filled by nodes)
    canned: str | None  # a full canned reply → skip the answerer entirely
    store: bool  # whether this turn may be written to history
    route: str
    queries: list[str]
    chunks: list[RetrievedChunk]
    low_relevance: bool


async def guardrail_node(state: ChatState) -> dict[str, Any]:
    """STEP 0 — input rail. Zero LLM calls; message is NEVER stored (Req 4)."""
    if check_input(state["question"]) is not None:
        return {"canned": deflection(), "store": False}
    return {}


async def context_node(state: ChatState) -> dict[str, Any]:
    """STEP 1 — no-docs check. The canned no-docs reply IS stored (E4 note)."""
    if not state["filenames"]:
        return {"canned": no_docs_message(), "store": True}
    return {}


async def rewrite_node(state: ChatState) -> dict[str, Any]:
    """STEP 2 — query rewrite (never raises; degrades to route=full internally)."""
    result = await rewrite(
        state["question"],
        state["history"],
        state["filenames"],
        state.get("cfg", DEFAULT),
    )
    update: dict[str, Any] = {"route": result.route, "queries": result.queries}
    if result.route == "direct":
        # Retrieval is skipped entirely; the answerer sees no context chunks.
        update.update({"chunks": [], "low_relevance": False})
    return update


async def retrieve_node(state: ChatState) -> dict[str, Any]:
    """STEP 3/4 — multi-query retrieval in the tenant's PINNED embedding space,
    over-fetching to `RETRIEVAL_POOL` so the reranker has candidates to cut."""
    cfg = state.get("cfg", DEFAULT)
    selection = await embed_signature.query_selection(state["session_id"], cfg)
    result = await retrieve(
        state["queries"],
        state["session_id"],
        embed_selection=selection,
        pool=get_settings().RETRIEVAL_POOL,
    )
    return {"chunks": result.chunks, "low_relevance": result.low_relevance}


async def rerank_node(state: ChatState) -> dict[str, Any]:
    """STEP 4.5 — open-source cross-encoder rerank (no-op when unavailable)."""
    chunks = await reranker.rerank(state["question"], state["chunks"])
    return {"chunks": chunks}


def _after_guardrail(state: ChatState) -> str:
    return "end" if state.get("canned") else "context"


def _after_context(state: ChatState) -> str:
    return "end" if state.get("canned") else "rewrite"


def _after_rewrite(state: ChatState) -> str:
    return "end" if state.get("route") == "direct" else "retrieve"


_graph: Any = None
_graph_failed = False  # remember a failed langgraph import; log the fallback once


def build_graph() -> Any:
    """Compile the StateGraph once (lazy langgraph import; None if unavailable)."""
    global _graph, _graph_failed
    if _graph is not None or _graph_failed:
        return _graph
    try:
        from langgraph.graph import END, StateGraph

        g = StateGraph(ChatState)
        g.add_node("guardrail", guardrail_node)
        g.add_node("context", context_node)
        g.add_node("rewrite", rewrite_node)
        g.add_node("retrieve", retrieve_node)
        g.add_node("rerank", rerank_node)
        g.set_entry_point("guardrail")
        g.add_conditional_edges("guardrail", _after_guardrail, {"context": "context", "end": END})
        g.add_conditional_edges("context", _after_context, {"rewrite": "rewrite", "end": END})
        g.add_conditional_edges("rewrite", _after_rewrite, {"retrieve": "retrieve", "end": END})
        g.add_edge("retrieve", "rerank")
        g.add_edge("rerank", END)
        _graph = g.compile()
    except ImportError as exc:
        _graph_failed = True
        _log.warning(
            "langgraph unavailable; chat runs the sequential fallback",
            extra={"reason": repr(exc)},
        )
    return _graph


async def _sequential(state: ChatState) -> ChatState:
    """The exact same nodes in the exact same order, without langgraph."""
    merged: ChatState = dict(state)  # type: ignore[assignment]
    merged.update(await guardrail_node(merged))
    if _after_guardrail(merged) == "end":
        return merged
    merged.update(await context_node(merged))
    if _after_context(merged) == "end":
        return merged
    merged.update(await rewrite_node(merged))
    if _after_rewrite(merged) == "end":
        return merged
    merged.update(await retrieve_node(merged))
    merged.update(await rerank_node(merged))
    return merged


async def prepare(state: ChatState) -> ChatState:
    """Run the pre-answer workflow → the final state chat_pipeline streams from.

    LangGraph when installed; the sequential fallback otherwise. A langgraph
    RUNTIME failure (not just import) also degrades to sequential — the nodes
    themselves never raise, so an error here is graph plumbing, not business
    logic.
    """
    graph = build_graph()
    if graph is not None:
        try:
            return await graph.ainvoke(state)
        except Exception as exc:  # noqa: BLE001 — plumbing failure degrades to sequential
            _log.warning("langgraph run failed; sequential fallback", extra={"error": repr(exc)})
    return await _sequential(state)
