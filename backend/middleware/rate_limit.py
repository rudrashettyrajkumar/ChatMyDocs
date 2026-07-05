"""Redis-backed upload quotas — the abuse shield for an auth-free endpoint
(ARCHITECTURE §7, spec E2 Req 1/deliverables).

Two independent counters guard `POST /documents`:

* **Session doc count** — derived live from the `dc:session:{sid}:docs` set
  size, never a separate counter. Deleting a document frees a slot
  immediately with no desync risk.
* **IP upload count** — a rolling 24h `INCR` counter (`dc:iplimit:{ip}`).
  DocChat has no auth, so this is the only thing stopping one visitor from
  burning the shared OpenRouter credit with junk uploads.

Both raise the shared `IngestValidationError` so `api/documents.py` can catch
every pre-stream rejection — validation, parsing, and rate limits alike — in
one place. A Redis OUTAGE, however, is not a rejection: per the "errors
degrade, never break" invariant, a quota check that can't reach Redis logs a
warning and lets the upload proceed rather than surfacing a raw 500 — an
unenforced quota beats a broken upload path.
"""

from __future__ import annotations

import logging

from backend.ingestion.errors import IngestValidationError
from backend.utils.config import get_settings
from backend.utils.redis_client import dc_key, get_redis

_log = logging.getLogger("docchat.rate_limit")
_IP_LIMIT_TTL_S = 24 * 3600


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
