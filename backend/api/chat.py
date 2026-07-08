"""`POST /chat/stream` (spec E4 deliverables, ARCHITECTURE §3.2/§7).

The question-limit check is the one synchronous pre-flight rejection (spec Req
5: "before any LLM call") — same validation-before-streaming split as
`documents.py`: everything after it commits to `text/event-stream`, so any
later failure surfaces only as a terminal SSE `error` event, never an HTTP
error code.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from backend.api.deps import get_tenant_id
from backend.llm.runconfig import BYOKError, from_headers
from backend.middleware.rate_limit import QuestionLimitExceeded, check_question_limit
from backend.pipeline.chat_pipeline import run_chat_pipeline
from backend.services.history import load_turns
from backend.utils.redis_client import dc_key, get_redis

router = APIRouter()
_log = logging.getLogger("docchat.api.chat")


class ChatRequest(BaseModel):
    question: str


async def _document_filenames(session_id: str) -> list[str]:
    """The session's uploaded filenames, for the no-docs check and rewriter context.

    Best-effort: a Redis outage degrades to an empty list, which routes the
    turn into the (harmless, if wrong) no-docs canned reply rather than a 500.
    """
    redis = get_redis()
    try:
        doc_ids = await redis.smembers(dc_key("session", session_id, "docs"))
        filenames: list[str] = []
        for doc_id in doc_ids:
            doc = await redis.hgetall(dc_key("doc", doc_id))
            filename = doc.get("filename")
            if filename:
                filenames.append(filename)
        return filenames
    except Exception as exc:  # noqa: BLE001 — a Redis outage must not break chat
        _log.warning("failed to load document list; degrading to empty", extra={"error": str(exc)})
        return []


@router.post("/chat/stream", response_model=None)
async def chat_stream(
    body: ChatRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    session_id: str = Depends(get_tenant_id),
) -> StreamingResponse | JSONResponse:
    # BYOK headers are validated BEFORE committing to the stream (same
    # validation-before-streaming split as documents.py) — a bad provider or
    # missing key is a fixable 400, not a mid-stream error event.
    try:
        cfg = from_headers(request.headers)
    except BYOKError as exc:
        return JSONResponse(status_code=400, content={"error": "byok_invalid", "detail": str(exc)})

    try:
        await check_question_limit(session_id)
    except QuestionLimitExceeded as exc:
        return JSONResponse(
            status_code=429, content={"error": "rate_limited", "detail": str(exc)}
        )

    filenames = await _document_filenames(session_id)
    history_turns = await load_turns(session_id)

    return StreamingResponse(
        run_chat_pipeline(
            question=body.question,
            session_id=session_id,
            history_turns=history_turns,
            filenames=filenames,
            background_tasks=background_tasks,
            cfg=cfg,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
