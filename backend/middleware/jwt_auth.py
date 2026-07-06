"""JWT auth — token minting and the request-identity dependencies.

We issue our OWN HS256 token at `/auth/login` and `/auth/register`; every
protected route then takes identity SOLELY from the verified `sub` claim, never
a client-supplied id. Any token problem yields a clean JSON 401, never a 500.

Two dependencies, by need:

* `get_current_user_id` — decode-only, no I/O. The multi-tenant key for the data
  routes (documents/chat): all they need is *which* account, and a valid
  signature already proves that. Keeping it Redis-free means the hot paths add
  no round-trip and stay trivially testable.
* `get_current_user` — additionally loads the account from Redis, for `/auth/me`
  where the caller wants the live profile (email, name, created_at).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from backend.services.users import AuthUnavailable, AuthUser, load_user
from backend.utils.config import get_settings

_log = logging.getLogger("docchat.auth")

JWT_ALGORITHM = "HS256"

# auto_error=False: raise our own uniform JSON 401 for a missing/blank header
# rather than FastAPI's terser default, so every failure mode looks identical.
_bearer = HTTPBearer(auto_error=False)


def _secret() -> str:
    secret = get_settings().JWT_SECRET
    if not secret:
        # An auth boundary must never sign/verify with an empty key; refuse
        # loudly. JWT_SECRET is REQUIRED_IN_PROD, so this only bites a misconfig.
        raise RuntimeError("JWT_SECRET is not configured")
    return secret


def issue_jwt(*, user_id: str, email: str, now: datetime | None = None) -> str:
    """Sign a token with claims {sub, email, exp} (TTL from config)."""
    now = now or datetime.now(UTC)
    ttl = timedelta(days=get_settings().JWT_TTL_DAYS)
    claims = {"sub": user_id, "email": email, "exp": now + ttl}
    return jwt.encode(claims, _secret(), algorithm=JWT_ALGORITHM)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing authentication.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _decode(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, _secret(), algorithms=[JWT_ALGORITHM])
    except JWTError as exc:
        # Bad signature, malformed token, and expiry are all auth failures
        # (ExpiredSignatureError is a JWTError subclass), never server errors.
        _log.info("jwt rejected", extra={"reason": repr(exc)})
        raise _unauthorized() from exc


async def get_current_user_id(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str:
    """The authenticated account id — the tenant key for every data route.

    Decode-only: a valid signature is proof of identity, so no Redis round-trip.
    """
    if creds is None or not creds.credentials:
        raise _unauthorized()
    sub = _decode(creds.credentials).get("sub")
    if not sub:
        raise _unauthorized()
    return sub


async def get_current_user(
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> AuthUser:
    """The live account behind the token — for `/auth/me` profile reads.

    A valid token for a since-deleted account is a 401 (the account is gone); a
    store outage is a 503 (we can't say), never a 500.
    """
    try:
        user = await load_user(user_id)
    except AuthUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sign-in temporarily unavailable. Please try again.",
        ) from exc
    if user is None:
        raise _unauthorized()
    return user
