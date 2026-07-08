"""Chat pipeline — the SSE face of the LangGraph workflow (`POST /chat/stream`).

v3 split of responsibilities: `graph/chat_graph.py` owns the pre-answer
workflow (guardrail → no-docs → rewrite → retrieve → rerank) as a StateGraph;
THIS module owns everything HTTP-shaped — SSE framing, heartbeats, the
streamed answer, history/quota post-processing, and turning failures into the
one terminal `error` event. The event contract (token/sources/done/error) is
FROZEN from E4; the graph rebuild must be invisible to the frontend.

Ambiguity calls carried over from E4 (unchanged):
- The no-docs canned reply IS stored in history; only guardrail-blocked
  messages are excluded.
- The daily question counter increments for EVERY question that reaches this
  pipeline, including the guardrail and no-docs exits.
- A mid-stream answer failure stores NOTHING (neither question nor partial
  answer).

BYOK addition: when the failing model is the USER'S (cfg.chat set), the error
event carries the gateway's `user_detail` — provider + model + reason — so the
user can fix their key instead of staring at a generic apology.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from fastapi import BackgroundTasks

from backend.agents.answer_agent import cited_sources, stream_answer
from backend.graph.chat_graph import ChatState, prepare
from backend.llm.gateway import LLMUnavailable
from backend.llm.runconfig import DEFAULT, RunConfig
from backend.middleware.rate_limit import increment_question_count
from backend.services import history
from backend.utils.sse import PING, format_event, format_token, with_heartbeat

_log = logging.getLogger("docchat.chat_pipeline")

_FRIENDLY_STREAM_ERROR = "Something went wrong while generating the answer. Please try again."


def _schedule_post_process(
    background_tasks: BackgroundTasks,
    *,
    session_id: str,
    question: str,
    answer_text: str | None,
    store: bool,
) -> None:
    """Final step — never awaited inline; always runs after the stream is sent."""
    background_tasks.add_task(increment_question_count, session_id)
    if store:
        background_tasks.add_task(history.append_turn, session_id, "user", question)
        if answer_text is not None:
            background_tasks.add_task(history.append_turn, session_id, "assistant", answer_text)


async def _emit_canned(
    text: str,
    *,
    background_tasks: BackgroundTasks,
    session_id: str,
    question: str,
    store: bool,
) -> AsyncIterator[str]:
    """A whole canned reply as one token frame + empty sources + done (spec Req 1)."""
    yield format_token(0, text)
    yield format_event("sources", {"sources": []})
    yield format_event("done", {})
    _schedule_post_process(
        background_tasks, session_id=session_id, question=question, answer_text=text, store=store
    )


def _stream_error_detail(exc: Exception) -> str:
    """User-facing detail for a failed answer stream (BYOK gets specifics)."""
    if isinstance(exc, LLMUnavailable):
        return exc.user_detail
    return _FRIENDLY_STREAM_ERROR


async def run_chat_pipeline(
    *,
    question: str,
    session_id: str,
    history_turns: list[dict[str, str]],
    filenames: list[str],
    background_tasks: BackgroundTasks,
    cfg: RunConfig = DEFAULT,
) -> AsyncIterator[str]:
    """The full chat turn, already SSE-formatted (spec E4 Req 1)."""
    # Pre-answer workflow: guardrail → no-docs → rewrite → retrieve → rerank.
    state: ChatState = {
        "question": question,
        "session_id": session_id,
        "history": history_turns,
        "filenames": filenames,
        "cfg": cfg,
    }
    final = await prepare(state)

    # A canned exit (guardrail block or no docs) skips the answerer entirely.
    if final.get("canned"):
        async for frame in _emit_canned(
            final["canned"],
            background_tasks=background_tasks,
            session_id=session_id,
            question=question,
            store=bool(final.get("store")),
        ):
            yield frame
        return

    chunks = final.get("chunks", [])
    low_relevance = bool(final.get("low_relevance"))

    # Streamed, cited answer (the one stage that talks to the user's model live).
    seq = 0
    answer_parts: list[str] = []
    try:
        token_stream = stream_answer(chunks, history_turns, question, low_relevance, cfg)
        async for token in with_heartbeat(token_stream):
            if token == PING:
                yield token  # heartbeat comment — no seq, passes straight through
                continue
            answer_parts.append(token)
            yield format_token(seq, token)
            seq += 1
    except Exception as exc:  # noqa: BLE001 — mid-stream failure degrades to one error event
        _log.warning("answer stream failed", extra={"error": repr(exc)})
        yield format_event("error", {"detail": _stream_error_detail(exc)})
        _schedule_post_process(
            background_tasks,
            session_id=session_id,
            question=question,
            answer_text=None,
            store=False,
        )
        return

    answer_text = "".join(answer_parts)
    yield format_event("sources", {"sources": cited_sources(chunks, answer_text)})
    yield format_event("done", {})

    # Background post-process: never blocks the stream.
    _schedule_post_process(
        background_tasks,
        session_id=session_id,
        question=question,
        answer_text=answer_text,
        store=True,
    )
