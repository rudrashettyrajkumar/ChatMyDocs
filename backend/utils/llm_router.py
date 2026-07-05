"""The single chokepoint for every LLM call in DocChat (ARCHITECTURE §4).

Agents NEVER import `litellm` directly — they call `complete(role, ...)` or
`stream(role, ...)` here. A "role" (`rewriter` / `answerer`) maps to a LiteLLM
Router deployment GROUP: the same `model_name` registered twice *is* the §4
failover chain, and LiteLLM rotates across the group on 429/5xx/timeout
(`num_retries=2`, `retry_after=0.5`). Role PRIMARIES come from env via
`config.py` (invariant #3 — a model migration is a one-line env change); only
the fixed Groq fallback is named here, the one infra spot allowed to.

One global `asyncio.Semaphore(MAX_CONCURRENT_LLM_CALLS)` wraps both public
calls. For `stream()` the slot is held for the WHOLE stream lifetime (released
in the generator's `finally`); a slot freed after mere connection setup would
let dozens of open streams burst a provider's RPM.

Every failover (a non-primary deployment served the call) is logged so free-
tier usage can be reviewed.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from backend.utils.config import Settings, get_settings

if TYPE_CHECKING:
    from litellm import Router

_log = logging.getLogger("docchat.llm_router")

# Per-role request timeout (seconds). Rewriter sits on the pre-retrieval hot
# path (spec E4 Req 6: rewrite 6s); the answerer streams a long cited reply
# (spec E4 Req 6: first-token 20s, generous because it covers the whole call).
ROLE_TIMEOUTS: dict[str, float] = {
    "rewriter": 6.0,
    "answerer": 20.0,
}

# Fixed fallback model id (ARCHITECTURE §4 table). Role primaries are env-driven
# (config.py); this Groq provider-contract string is the pinned failover link of
# both chains — a deliberately diverse second provider so one OpenRouter outage
# isn't total. Its FREE limits should be re-verified periodically.
_GROQ_70B = "groq/llama-3.3-70b-versatile"


def _key_for(model: str, s: Settings) -> str | None:
    """The provider credential matching a model id's `provider/` prefix.

    Lets a role's env primary migrate to any provider (invariant #3) without
    touching this module: the right key is picked from the id alone. Defaults to
    OpenRouter, the primary gateway.
    """
    if model.startswith("groq/"):
        return s.GROQ_API_KEY
    return s.OPENROUTER_API_KEY


def _dep(name: str, model: str, s: Settings) -> dict[str, Any]:
    """One Router deployment: a role `name` bound to a model + its provider key."""
    return {
        "model_name": name,
        "litellm_params": {"model": model, "api_key": _key_for(model, s)},
    }


def _build_model_list(s: Settings) -> list[dict[str, Any]]:
    """The two §4 failover chains, ordered primary-first per role.

    Order within each `model_name` group is the failover order: an env-driven
    OpenRouter primary then the pinned Groq fallback.
    """
    return [
        _dep("rewriter", s.REWRITER_MODEL, s),
        _dep("rewriter", _GROQ_70B, s),
        _dep("answerer", s.ANSWERER_MODEL, s),
        _dep("answerer", _GROQ_70B, s),
    ]


_router: Router | None = None
_semaphore: asyncio.Semaphore | None = None


def _get_router() -> Router:
    """Lazily build the shared Router singleton (heavy import deferred)."""
    global _router
    if _router is None:
        from litellm import Router

        _router = Router(
            model_list=_build_model_list(get_settings()),
            num_retries=2,
            retry_after=0.5,
        )
    return _router


def _get_semaphore() -> asyncio.Semaphore:
    """Lazily build the global concurrency gate (bound to the running loop)."""
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(get_settings().MAX_CONCURRENT_LLM_CALLS)
    return _semaphore


def _check_role(role: str) -> float:
    """Return the role's timeout, or fail loudly on an unknown role."""
    try:
        return ROLE_TIMEOUTS[role]
    except KeyError:
        raise ValueError(f"unknown LLM role: {role!r}") from None


def _bare(model_id: str) -> str:
    """Drop the `provider/` prefix so a served model compares to a config id."""
    return model_id.split("/")[-1]


def _primary_for(role: str) -> str:
    """The env-configured primary model id for a role."""
    s = get_settings()
    return {"rewriter": s.REWRITER_MODEL, "answerer": s.ANSWERER_MODEL}[role]


def _log_failover(role: str, served_model: str | None) -> None:
    """Log a structured failover event when a non-primary deployment served."""
    if not served_model:
        return
    primary = _primary_for(role)
    if _bare(served_model) == _bare(primary):
        return
    _log.warning(
        "llm failover",
        extra={
            "event": "llm_failover",
            "role": role,
            "from_provider": primary,
            "to_provider": served_model,
            "reason": "primary unavailable; served by fallback deployment",
        },
    )


def _token_of(chunk: Any) -> str:
    """Best-effort text delta from a streaming chunk ('' if none)."""
    try:
        return chunk.choices[0].delta.content or ""
    except (AttributeError, IndexError, TypeError):
        return ""


async def complete(role: str, messages: list[dict[str, Any]], **kw: Any) -> Any:
    """Non-streaming completion for `role`, through the semaphore + failover chain.

    Returns the raw LiteLLM response (agents read `.choices[0].message.content`).
    Acquiring/releasing the slot is scoped to the single round-trip.
    """
    timeout = _check_role(role)
    async with _get_semaphore():
        response = await _get_router().acompletion(
            model=role, messages=messages, timeout=timeout, **kw
        )
    _log_failover(role, getattr(response, "model", None))
    return response


async def stream(role: str, messages: list[dict[str, Any]], **kw: Any) -> AsyncIterator[str]:
    """Stream text tokens for `role`, holding the semaphore for the whole stream.

    The slot is acquired before the call and released in `finally` only after the
    last token — see the module docstring on RPM bursting. Any failure (before or
    mid-stream) propagates to the caller, which degrades it into an SSE error event
    (DocChat has no restart/resume contract, unlike the MyShiva reference).
    """
    timeout = _check_role(role)
    sem = _get_semaphore()
    await sem.acquire()
    served_seen = False
    try:
        response = await _get_router().acompletion(
            model=role, messages=messages, stream=True, timeout=timeout, **kw
        )
        async for chunk in response:
            if not served_seen:
                served_seen = True
                _log_failover(role, getattr(chunk, "model", None))
            token = _token_of(chunk)
            if token:
                yield token
    finally:
        sem.release()
