"""Shared FastAPI dependencies (spec E1 Req 4).

DocChat has no auth: an anonymous `X-Session-Id` (client-generated UUID v4,
ARCHITECTURE §7) is the only tenant boundary. Every route that touches
per-session data depends on `get_session_id` so a missing/malformed header
fails the request before any handler logic runs.
"""

from __future__ import annotations

import uuid

from fastapi import Header, HTTPException, status

_MISSING_DETAIL = "X-Session-Id header is required"
_MALFORMED_DETAIL = "X-Session-Id must be a valid UUID v4"


async def get_session_id(
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
) -> str:
    """Validate the `X-Session-Id` header and return it normalized (lowercase).

    400 on missing or malformed input — never a 500, never a silently-generated
    session (that would let a client claim someone else's documents).
    """
    if not x_session_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_MISSING_DETAIL)
    try:
        parsed = uuid.UUID(x_session_id)
    except (ValueError, AttributeError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=_MALFORMED_DETAIL
        ) from exc
    if parsed.version != 4:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_MALFORMED_DETAIL)
    return str(parsed)
