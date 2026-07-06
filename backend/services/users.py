"""User accounts — Upstash-backed, self-contained email/password auth.

Unlike every other DocChat Redis key, user records carry **no TTL**: an account
outlives the 24h document/history window (that is the whole point of signing in).
Two keys per user, written in one pipeline so they never desync:

    dc:user:{email}     hash → {id, email, name, password_hash, created_at}
    dc:userid:{id}      string → email        (reverse lookup for the JWT `sub`)

Email is the natural unique key, lower-cased/trimmed so `Foo@x.com` and
`foo@x.com ` are the same account. The id is a server-minted UUIDv4 and is what
every downstream tenant boundary (Qdrant filter, `dc:session:*`, history) keys on.

Auth is a security boundary, so — unlike the data paths that "degrade, never
break" — a Redis outage here raises `AuthUnavailable`: we must never silently
treat an unreachable store as "no such user" or "password OK".
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from backend.utils.redis_client import dc_key, get_redis
from backend.utils.security import hash_password, verify_password


@dataclass(frozen=True)
class AuthUser:
    """The public identity attached to a request — never carries the hash."""

    id: str
    email: str
    name: str | None
    created_at: float


class EmailAlreadyRegistered(Exception):
    """Signup attempted with an email that already has an account (→ 409)."""


class InvalidCredentials(Exception):
    """Login email unknown or password wrong (→ 401, identical message either way)."""


class AuthUnavailable(Exception):
    """The user store could not be reached — auth can't be decided (→ 503)."""


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _user_key(email: str) -> str:
    return dc_key("user", _normalize_email(email))


def _id_key(user_id: str) -> str:
    return dc_key("userid", user_id)


def _to_user(record: dict[str, str]) -> AuthUser:
    return AuthUser(
        id=record["id"],
        email=record["email"],
        name=record.get("name") or None,
        created_at=float(record.get("created_at", 0.0)),
    )


async def register_user(email: str, password: str, name: str | None = None) -> AuthUser:
    """Create a new account. Raises `EmailAlreadyRegistered` / `AuthUnavailable`.

    The email→record and id→email keys are written together (pipeline) so a
    partially-created user can never exist.
    """
    email_norm = _normalize_email(email)
    redis = get_redis()
    try:
        existing = await redis.hgetall(_user_key(email_norm))
        if existing:
            raise EmailAlreadyRegistered(email_norm)

        user_id = str(uuid.uuid4())
        created_at = time.time()
        clean_name = (name or "").strip() or None
        await redis.pipeline(
            (
                "HSET",
                _user_key(email_norm),
                "id",
                user_id,
                "email",
                email_norm,
                "name",
                clean_name or "",
                "password_hash",
                hash_password(password),
                "created_at",
                created_at,
            ),
            ("SET", _id_key(user_id), email_norm),
        )
    except EmailAlreadyRegistered:
        raise
    except Exception as exc:  # noqa: BLE001 — an auth store outage must not read as "created"
        raise AuthUnavailable(str(exc)) from exc
    return AuthUser(id=user_id, email=email_norm, name=clean_name, created_at=created_at)


async def authenticate(email: str, password: str) -> AuthUser:
    """Return the user iff the password verifies. Raises `InvalidCredentials`.

    Same exception for unknown-email and wrong-password so the response can't be
    used to enumerate which emails have accounts.
    """
    redis = get_redis()
    try:
        record = await redis.hgetall(_user_key(email))
    except Exception as exc:  # noqa: BLE001 — can't verify ⇒ 503, never a false accept
        raise AuthUnavailable(str(exc)) from exc
    if not record or not verify_password(password, record.get("password_hash", "")):
        raise InvalidCredentials
    return _to_user(record)


async def load_user(user_id: str) -> AuthUser | None:
    """Resolve a JWT `sub` to the current account, or None if it's gone.

    Raises `AuthUnavailable` on a store outage so a protected route returns 503
    rather than pretending the (validly-tokened) user no longer exists.
    """
    redis = get_redis()
    try:
        email = await redis.get(_id_key(user_id))
        if not email:
            return None
        record = await redis.hgetall(_user_key(email))
    except Exception as exc:  # noqa: BLE001
        raise AuthUnavailable(str(exc)) from exc
    return _to_user(record) if record else None
