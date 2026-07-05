"""Chat history — Redis-backed short-term memory (ARCHITECTURE §3.2 steps 1/6,
spec E4 Req 4).

Key `dc:history:{session_id}` is a Redis list, newest turn at the head (LPUSH),
trimmed to `_WINDOW` entries, TTL refreshed on every append. Turns are stored
OLDEST-FIRST once loaded (`load_turns` reverses the list) since every downstream
consumer (rewrite_agent, prompt_assembly) already expects that order and slices
its own shorter window off the end.

Guardrail-blocked messages are never appended — the injection text must never be
replayed into a later prompt (CLAUDE.md invariant 1). Every other turn, including
route=direct answers, is stored the same way (spec Req 4).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from backend.utils.config import get_settings
from backend.utils.redis_client import dc_key, get_redis

_log = logging.getLogger("docchat.history")

# LTRIM 12 (spec Req 4) — 6 exchanges' worth of {role, content, ts} entries.
_WINDOW = 12


def _key(session_id: str) -> str:
    return dc_key("history", session_id)


async def load_turns(session_id: str) -> list[dict[str, Any]]:
    """Up to `_WINDOW` stored turns, OLDEST FIRST.

    Degrades to `[]` on any Redis failure or corrupt entry (errors degrade, never
    break) — a chat turn with no history is still answerable.
    """
    try:
        raw = await get_redis().lrange(_key(session_id), 0, _WINDOW - 1)
    except Exception as exc:  # noqa: BLE001 — a Redis outage must not break chat
        _log.warning("history load failed; degrading to empty", extra={"error": str(exc)})
        return []
    turns: list[dict[str, Any]] = []
    for item in raw:
        try:
            turns.append(json.loads(item))
        except (ValueError, TypeError):
            continue  # a corrupt entry is skipped, not fatal
    turns.reverse()  # LPUSH stores newest-first; every consumer wants oldest-first
    return turns


async def append_turn(session_id: str, role: str, content: str) -> None:
    """LPUSH one `{role, content, ts}` turn, LTRIM to the window, refresh TTL.

    Best-effort: a failed append degrades the session's NEXT turn to less
    history; it never breaks the turn currently in flight.
    """
    settings = get_settings()
    key = _key(session_id)
    payload = json.dumps({"role": role, "content": content, "ts": time.time()})
    try:
        await get_redis().pipeline(
            ("LPUSH", key, payload),
            ("LTRIM", key, 0, _WINDOW - 1),
            ("EXPIRE", key, settings.SESSION_TTL_HOURS * 3600),
        )
    except Exception as exc:  # noqa: BLE001 — a Redis outage must not break chat
        _log.warning("history append failed", extra={"error": str(exc)})
