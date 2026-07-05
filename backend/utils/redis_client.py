"""Upstash Redis over its REST API (not redis://).

REST fits the free tier and a single small container: no connection pool to
keep warm, no TCP socket per worker, just HTTPS calls authenticated with a
bearer token. Each command is POSTed as a JSON array (`["LPUSH", key, value]`)
and the reply comes back as `{"result": ...}`.

The wrapper exposes only the verbs DocChat needs (chat history lists, document
metadata, rate-limit counters). The underlying `httpx.AsyncClient` is a lazy
module-level singleton so the connection/header setup happens once.

Every DocChat key is prefixed `dc:` (ARCHITECTURE §2) so it shares the Upstash
instance with other apps without collision — see `dc_key()`.
"""

from collections.abc import Sequence
from typing import Any

import httpx

from backend.utils.config import get_settings

# Upstash REST calls are tiny once the connection is warm (~200ms), but the
# FIRST call pays the full TLS handshake — measured >2s cold. 2.5s absorbs the
# cold start while still keeping a wedged cache from stalling the request path
# (errors degrade, never break); `warm_up()` at app startup pays the handshake
# before user traffic arrives.
REDIS_TIMEOUT_S = 2.5


def dc_key(*parts: str) -> str:
    """Build a `dc:`-prefixed Redis key from parts, e.g. `dc_key("history", sid)`."""
    return ":".join(("dc", *parts))


class UpstashRedis:
    """Thin async wrapper over the Upstash REST command endpoint."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def _command(self, *args: Any) -> Any:
        """POST one Redis command and return its `result` field."""
        resp = await self._client.post("/", json=[str(a) for a in args])
        resp.raise_for_status()
        return resp.json()["result"]

    async def lpush(self, key: str, *values: Any) -> int:
        return await self._command("LPUSH", key, *values)

    async def rpush(self, key: str, *values: Any) -> int:
        return await self._command("RPUSH", key, *values)

    async def ltrim(self, key: str, start: int, stop: int) -> str:
        return await self._command("LTRIM", key, start, stop)

    async def lrange(self, key: str, start: int, stop: int) -> list[str]:
        return await self._command("LRANGE", key, start, stop)

    async def expire(self, key: str, seconds: int) -> int:
        return await self._command("EXPIRE", key, seconds)

    async def get(self, key: str) -> str | None:
        return await self._command("GET", key)

    async def setex(self, key: str, seconds: int, value: Any) -> str:
        return await self._command("SETEX", key, seconds, value)

    async def incr(self, key: str) -> int:
        return await self._command("INCR", key)

    async def delete(self, key: str) -> int:
        return await self._command("DEL", key)

    async def sadd(self, key: str, *values: Any) -> int:
        return await self._command("SADD", key, *values)

    async def srem(self, key: str, *values: Any) -> int:
        return await self._command("SREM", key, *values)

    async def smembers(self, key: str) -> list[str]:
        result = await self._command("SMEMBERS", key)
        return result or []

    async def hset(self, key: str, mapping: dict[str, Any]) -> int:
        fields: list[Any] = []
        for field, value in mapping.items():
            fields.extend((field, value))
        return await self._command("HSET", key, *fields)

    async def hgetall(self, key: str) -> dict[str, str]:
        """Upstash returns a flat `[field, value, field, value, ...]` array;
        pair it up into a dict (`{}` for a missing/expired key)."""
        flat = await self._command("HGETALL", key)
        if not flat:
            return {}
        return dict(zip(flat[0::2], flat[1::2], strict=True))

    async def pipeline(self, *commands: Sequence[Any]) -> list[Any]:
        """Send several commands in ONE HTTP round-trip via Upstash's `/pipeline`
        endpoint. Each command is a sequence like `("LPUSH", key, v1, v2)`; the
        body is a JSON array of those arrays and Upstash replies with one
        `{"result": ...}` per command, in order. Every arg is stringified, as
        with `_command`.
        """
        body = [[str(a) for a in cmd] for cmd in commands]
        resp = await self._client.post("/pipeline", json=body)
        resp.raise_for_status()
        return [item["result"] for item in resp.json()]


_redis: UpstashRedis | None = None


def get_redis() -> UpstashRedis:
    """Return the shared Upstash REST client, building it once."""
    global _redis
    if _redis is None:
        settings = get_settings()
        client = httpx.AsyncClient(
            base_url=settings.UPSTASH_URL,
            headers={"Authorization": f"Bearer {settings.UPSTASH_TOKEN}"},
            timeout=REDIS_TIMEOUT_S,
        )
        _redis = UpstashRedis(client)
    return _redis


async def warm_up() -> None:
    """Pay the TLS handshake at app startup so the first user request doesn't.

    Best-effort: a failure is logged by the caller's boundary and boot continues
    — the cache warms on first use instead (errors degrade, never break).
    """
    await get_redis().get(dc_key("health", "ping"))
