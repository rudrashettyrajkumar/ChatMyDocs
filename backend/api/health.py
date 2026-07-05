"""Health endpoint — per-dependency status (ARCHITECTURE §7, §9; spec E1 Req 5).

UptimeRobot polls `/health` every 5 min (ARCHITECTURE §9), so every check is
cheap: Qdrant `/collections`, a Redis GET, and the LLM gateway's `/models`
list — reachability + auth, never a paid completion call.

Aggregation: one or more deps down ⇒ `degraded` (still HTTP 200, the app can
serve whatever still works); every dep down ⇒ 503 (truly dark). Each probe has
a hard timeout and degrades to "down" on any error — a health check must never
hang or raise.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.utils.config import get_settings
from backend.utils.qdrant_client import QDRANT_TIMEOUT_S, get_qdrant
from backend.utils.redis_client import REDIS_TIMEOUT_S, dc_key, get_redis

router = APIRouter()
_log = logging.getLogger("docchat.health")

# Cheap: OpenRouter's model catalog is a free, unauthenticated-cost GET — it
# proves the gateway is reachable (and the key valid, since we pass it) without
# spending a token.
LLM_PING_TIMEOUT_S = 2.0
_OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"

_OK = "ok"
_DOWN = "down"


async def _check_qdrant() -> bool:
    await asyncio.wait_for(get_qdrant().get_collections(), timeout=QDRANT_TIMEOUT_S)
    return True


async def _check_redis() -> bool:
    # A GET of a throwaway key exercises auth + round-trip without writing.
    await asyncio.wait_for(get_redis().get(dc_key("health", "ping")), timeout=REDIS_TIMEOUT_S)
    return True


async def _check_llm() -> bool:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=LLM_PING_TIMEOUT_S) as http:
        resp = await http.get(
            _OPENROUTER_MODELS_URL,
            headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}"},
        )
        resp.raise_for_status()
    return True


async def _probe(name: str, check: Callable[[], Awaitable[bool]]) -> str:
    """Run one check, degrading any failure to "down" (never raises)."""
    try:
        await check()
        return _OK
    except Exception as exc:  # noqa: BLE001 — a probe must absorb everything
        _log.warning("health check failed", extra={"dep": name, "error": str(exc)})
        return _DOWN


@router.get("/health")
async def health() -> JSONResponse:
    qdrant, redis, llm = await asyncio.gather(
        _probe("qdrant", _check_qdrant),
        _probe("redis", _check_redis),
        _probe("llm", _check_llm),
    )
    deps = {"qdrant": qdrant, "redis": redis, "llm": llm}
    down = [v for v in deps.values() if v == _DOWN]

    if len(down) == len(deps):
        status_str, code = "degraded", 503  # everything dark
    elif down:
        status_str, code = "degraded", 200
    else:
        status_str, code = "ok", 200

    return JSONResponse(status_code=code, content={"status": status_str, **deps})
