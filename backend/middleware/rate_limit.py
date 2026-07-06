"""Redis-backed request quotas — the abuse shield for auth-free endpoints
(ARCHITECTURE §7, spec E2 Req 1/deliverables, spec E4 Req 5).

Independent counters guard the two write paths:

* **Session doc count** — derived live from the `dc:session:{sid}:docs` set
  size, never a separate counter. Deleting a document frees a slot
  immediately with no desync risk.
* **IP upload count** — a rolling 24h `INCR` counter (`dc:iplimit:{ip}`).
  DocChat has no auth, so this is the only thing stopping one visitor from
  burning the shared OpenRouter credit with junk uploads.
* **Session question count** (`dc:qcount:{sid}`) — a rolling 24h counter for
  `POST /chat/stream` (spec E4 Req 5). Split into a GET-only check and a
  separate increment so the check can run BEFORE any LLM call while the
  increment stays a cheap post-stream `BackgroundTask` (ARCHITECTURE §3.2 step
  6) — a request that never reaches the answer step still counts once it was
  asked, but the increment itself never blocks the response.

All raise on rejection (`IngestValidationError` for uploads, `QuestionLimitExceeded`
for chat) so the API layer can turn every pre-stream rejection into a friendly 4xx
in one place. A Redis OUTAGE, however, is not a rejection: per the "errors degrade,
never break" invariant, a quota check that can't reach Redis logs a warning and lets
the request proceed rather than surfacing a raw 500 — an unenforced quota beats a
broken request path.
"""

from __future__ import annotations

import logging

from backend.ingestion.errors import IngestValidationError
from backend.utils.config import get_settings
from backend.utils.redis_client import dc_key, get_redis

_log = logging.getLogger("docchat.rate_limit")
_IP_LIMIT_TTL_S = 24 * 3600


class QuestionLimitExceeded(Exception):
    """The session has already asked `MAX_QUESTIONS_PER_DAY` questions today."""


async def check_session_doc_limit(session_id: str) -> None:
    """Reject once a session already holds `MAX_DOCS_PER_SESSION` documents."""
    settings = get_settings()
    try:
        count = len(await get_redis().smembers(dc_key("session", session_id, "docs")))
    except Exception as exc:  # noqa: BLE001 — Redis outage must not break uploads
        _log.warning("session doc count check failed; allowing upload", extra={"error": str(exc)})
        return
    if count >= settings.MAX_DOCS_PER_SESSION:
        raise IngestValidationError(
            "too_many_documents",
            f"This session already has {count} documents "
            f"(limit {settings.MAX_DOCS_PER_SESSION}). Delete one first.",
            status_code=400,
        )


async def check_and_increment_ip_upload(client_ip: str) -> None:
    """Bump the IP's daily upload counter; reject once it exceeds the cap.

    The TTL is set only on the FIRST increment of the window so it always
    expires ~24h after that first upload, not after every subsequent one.
    """
    settings = get_settings()
    redis = get_redis()
    key = dc_key("iplimit", client_ip)
    try:
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, _IP_LIMIT_TTL_S)
    except Exception as exc:  # noqa: BLE001 — Redis outage must not break uploads
        _log.warning("IP upload count check failed; allowing upload", extra={"error": str(exc)})
        return
    if count > settings.MAX_UPLOADS_PER_IP_DAY:
        raise IngestValidationError(
            "upload_limit_exceeded",
            "Upload limit reached for today. Please try again tomorrow.",
            status_code=429,
        )


def _qcount_key(session_id: str) -> str:
    return dc_key("qcount", session_id)


async def check_question_limit(session_id: str) -> None:
    """GET-only pre-check — must run before any LLM call (spec Req 5).

    Reads the counter without incrementing it: the paired INCR happens in
    `increment_question_count`, run as a post-stream BackgroundTask so a
    request that fails before the answer step doesn't burn a slot twice and a
    slow answer doesn't delay the response with a write.
    """
    settings = get_settings()
    try:
        raw = await get_redis().get(_qcount_key(session_id))
    except Exception as exc:  # noqa: BLE001 — a Redis outage must not break chat
        _log.warning("question limit check failed; allowing", extra={"error": str(exc)})
        return
    count = int(raw) if raw else 0
    if count >= settings.MAX_QUESTIONS_PER_DAY:
        raise QuestionLimitExceeded(
            f"Daily question limit reached ({settings.MAX_QUESTIONS_PER_DAY}/day). "
            "Please try again tomorrow."
        )


async def increment_question_count(session_id: str) -> None:
    """Bump the session's daily question counter; TTL set only on the first hit."""
    settings = get_settings()
    key = _qcount_key(session_id)
    try:
        count = await get_redis().incr(key)
        if count == 1:
            await get_redis().expire(key, settings.SESSION_TTL_HOURS * 3600)
    except Exception as exc:  # noqa: BLE001 — a Redis outage must not break chat
        _log.warning("question count increment failed", extra={"error": str(exc)})
