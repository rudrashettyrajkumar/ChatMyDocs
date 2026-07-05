"""Chat pipeline — the async orchestrator for `POST /chat/stream`
(ARCHITECTURE §3.2, spec E4 Req 1).

**Pipeline order is LAW**: guardrail → no-docs check → rewrite →
(route=direct skips retrieval) → retrieve → streamed cited answer →
BackgroundTasks post-process. One linear async generator, no framework — same
"boring beats clever" philosophy as every other DocChat agent.

Every yielded item is an already-formatted SSE frame (`backend/utils/sse.py`
helpers), so `api/chat.py` only wraps this generator in a `StreamingResponse`;
nothing downstream re-parses or re-formats an event.

Ambiguity calls (spec doesn't say, smallest reasonable choice):
- The no-docs canned reply IS stored in history like any normal turn — only
  guardrail-blocked messages are excluded (spec Req 4 only calls out the
  guardrail path as excluded).
- The daily question counter (`increment_question_count`) is incremented for
  EVERY question that reaches this pipeline, including the guardrail and
  no-docs exits — "questions/session/day" is a count of questions asked, not
  just ones that reached an LLM.
- A mid-stream answer failure stores NOTHING (neither the question nor the
  partial answer) — a broken turn is worse to replay into a future prompt than
  one the user can simply re-ask.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from fastapi import BackgroundTasks

from backend.agents.answer_agent import cited_sources, stream_answer
from backend.agents.retrieval_agent import RetrievedChunk, retrieve
from backend.agents.rewrite_agent import rewrite
from backend.middleware.rate_limit import increment_question_count
from backend.services import history
from backend.utils.guardrails import check_input, deflection
from backend.utils.prompt_assembly import no_docs_message
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
    """STEP 6 — never awaited inline; always runs after the stream is sent."""
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


async def run_chat_pipeline(
    *,
    question: str,
    session_id: str,
    history_turns: list[dict[str, str]],
    filenames: list[str],
    background_tasks: BackgroundTasks,
) -> AsyncIterator[str]:
    """The full chat turn, already SSE-formatted (spec E4 Req 1)."""
    # STEP 0 — input guardrail. Zero LLM calls; message is NEVER stored (Req 4).
    if check_input(question) is not None:
        async for frame in _emit_canned(
            deflection(),
            background_tasks=background_tasks,
            session_id=session_id,
            question=question,
            store=False,
        ):
            yield frame
        return

    # STEP 1 — context load / no-docs check. No LLM call.
    if not filenames:
        async for frame in _emit_canned(
            no_docs_message(),
            background_tasks=background_tasks,
            session_id=session_id,
            question=question,
            store=True,
        ):
            yield frame
        return

    # STEP 2 — query rewrite (never raises; degrades to route=full internally).
    rewrite_result = await rewrite(question, history_turns, filenames)

    # STEP 3/4 — retrieval, skipped entirely for route=direct.
    chunks: list[RetrievedChunk]
    if rewrite_result.route == "direct":
        chunks, low_relevance = [], False
    else:
        result = await retrieve(rewrite_result.queries, session_id)
        chunks, low_relevance = result.chunks, result.low_relevance

    # STEP 5 — streamed, cited answer.
    seq = 0
    answer_parts: list[str] = []
    try:
        token_stream = stream_answer(chunks, history_turns, question, low_relevance)
        async for token in with_heartbeat(token_stream):
            if token == PING:
                yield token  # heartbeat comment — no seq, passes straight through
                continue
            answer_parts.append(token)
            yield format_token(seq, token)
            seq += 1
    except Exception as exc:  # noqa: BLE001 — mid-stream failure degrades to one error event
        _log.warning("answer stream failed", extra={"error": repr(exc)})
        yield format_event("error", {"detail": _FRIENDLY_STREAM_ERROR})
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

    # STEP 6 — background post-process: never blocks the stream.
    _schedule_post_process(
        background_tasks,
        session_id=session_id,
        question=question,
        answer_text=answer_text,
        store=True,
    )
