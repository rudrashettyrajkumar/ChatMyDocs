"""Query rewrite agent — question + history → route + standalone queries.

ARCHITECTURE §3.2 step 2, spec E3 Req 1. One call to the `rewriter` gateway
role (role timeout 6s, set in gateway.ROLE_TIMEOUTS; BYOK-aware via the
request's `RunConfig`) turns the raw user turn into the strict control signal
the rest of the chat pipeline runs on:
`route` (direct = answer from history alone, retrieval skipped; full = normal
RAG) and 2-4 standalone English `queries` for multi-query retrieval.

Degraded beats broken (MyShiva detection_agent.py DEFAULT_DETECTION pattern,
docchat-conventions skill): ANY failure on this pre-retrieval hot path — LLM
timeout/error, malformed JSON, a missing field, an out-of-enum route — falls
back to `Rewrite(route="full", queries=[question])`, logged with its reason.
This module never raises out to the pipeline.

Ambiguity call: spec Req 1 says queries are "2-4" but route=direct skips
retrieval entirely (ARCHITECTURE §3.2), so its queries are never consumed —
the 2-4 count is enforced only when route=="full"; a direct reply may return
an empty queries array without tripping the safe-default path.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ValidationError, field_validator

from backend.llm import gateway
from backend.llm.runconfig import DEFAULT, RunConfig

_log = logging.getLogger("docchat.rewrite_agent")

# Show the model only the last 6 turns (ARCHITECTURE §3.2 short-term window).
_HISTORY_TURNS = 6
_MIN_QUERIES = 2
_MAX_QUERIES = 4
# If the question itself is empty (shouldn't happen via the API, but degrade safely).
_BROAD_FALLBACK_QUERY = "What does the document say?"

_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "rewriter.md"
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$")


class Rewrite(BaseModel):
    """The validated E3 control signal: retrieval route + standalone queries."""

    route: Literal["direct", "full"]
    queries: list[str]

    @field_validator("route", mode="before")
    @classmethod
    def _normalize_route(cls, value: Any) -> Any:
        """Lowercase + strip so 'Full'/'DIRECT ' pass the Literal check."""
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("queries", mode="after")
    @classmethod
    def _clean_queries(cls, value: list[str]) -> list[str]:
        """Drop blank/non-string entries (keeps retrieval input clean)."""
        return [q.strip() for q in value if isinstance(q, str) and q.strip()]


class _ParseError(Exception):
    """A categorized reason the model output could not become a valid Rewrite."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


async def rewrite(
    question: str,
    history: list[dict[str, Any]] | None = None,
    filenames: list[str] | None = None,
    cfg: RunConfig = DEFAULT,
) -> Rewrite:
    """Turn one user turn into a validated `Rewrite` (never raises).

    `history` is recent turns (oldest-first, dicts with `role`/`content`); only
    the last 6 are shown to the model. `filenames` are the session's uploaded
    document names, given as context for what "the document" refers to. `cfg`
    carries the request's BYOK model selection (demo default otherwise). Any
    failure -> the safe default (`route=full`, `queries=[question]`), logged
    with its reason.
    """
    messages = _build_messages(question, history or [], filenames or [])
    try:
        text = await gateway.complete("rewriter", messages, cfg, json_mode=True)
    except Exception as exc:  # noqa: BLE001 — boundary: any LLM/timeout failure degrades
        return _default_rewrite(question, f"llm_call_failed: {exc!r}")
    try:
        return _to_rewrite(_loads(text))
    except _ParseError as exc:
        return _default_rewrite(question, exc.reason)


def _to_rewrite(data: dict[str, Any]) -> Rewrite:
    """Validate the parsed dict into a Rewrite; raise `_ParseError` on rejection."""
    try:
        parsed = Rewrite.model_validate(data)
    except ValidationError as exc:
        raise _ParseError(f"schema_invalid: {_first_error(exc)}") from exc
    if parsed.route == "full" and not (_MIN_QUERIES <= len(parsed.queries) <= _MAX_QUERIES):
        raise _ParseError("query_count_out_of_range")
    return parsed


def _loads(raw: str) -> dict[str, Any]:
    """Strip accidental ```json fences → json.loads → require a JSON object."""
    text = raw.strip()
    if text.startswith("```"):
        text = _FENCE_RE.sub("", text).strip()
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise _ParseError(f"json_decode_failed: {exc}") from exc
    if not isinstance(parsed, dict):
        raise _ParseError("output_not_a_json_object")
    return parsed


def _first_error(exc: ValidationError) -> str:
    """A compact 'field: message' for the log (the full pydantic dump is noisy)."""
    errors = exc.errors()
    if not errors:
        return "unknown"
    first = errors[0]
    loc = ".".join(str(part) for part in first.get("loc", ())) or "?"
    return f"{loc}: {first.get('msg', '')}"


def _build_messages(
    question: str, history: list[dict[str, Any]], filenames: list[str]
) -> list[dict[str, str]]:
    """System prompt (the versioned IP) + a user turn carrying files, history, question."""
    return [
        {"role": "system", "content": _prompt()},
        {"role": "user", "content": _user_turn(question, history, filenames)},
    ]


def _user_turn(question: str, history: list[dict[str, Any]], filenames: list[str]) -> str:
    return (
        f"FILES: {', '.join(filenames) if filenames else '(none uploaded)'}\n\n"
        f"HISTORY (oldest first, last 6 turns):\n{_format_history(history)}\n\n"
        f'QUESTION:\n"""\n{question}\n"""\n\n'
        "Return ONLY the rewrite JSON object now."
    )


def _format_history(history: list[dict[str, Any]]) -> str:
    """Last 6 turns as `role: content` lines; malformed entries are skipped (degrade)."""
    lines: list[str] = []
    for turn in history[-_HISTORY_TURNS:]:
        if not isinstance(turn, dict):
            continue
        role = str(turn.get("role", "user")).strip() or "user"
        content = str(turn.get("content", "")).strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines) if lines else "(no prior turns)"


_PROMPT_CACHE: str | None = None


def _prompt() -> str:
    """Lazily read + cache the rewriter system prompt (the versioned IP)."""
    global _PROMPT_CACHE
    if _PROMPT_CACHE is None:
        _PROMPT_CACHE = _PROMPT_PATH.read_text(encoding="utf-8")
    return _PROMPT_CACHE


def _default_rewrite(question: str, reason: str) -> Rewrite:
    """Degraded-but-answerable fallback (MyShiva DEFAULT_DETECTION pattern).

    The user's own message becomes the single retrieval query so the chat
    pipeline still gets relevant chunks; logged with the precise `reason`.
    """
    _log.warning(
        "rewrite fallback",
        extra={"event": "rewrite_fallback", "fallback_reason": reason},
    )
    query = question.strip()[:200] or _BROAD_FALLBACK_QUERY
    return Rewrite(route="full", queries=[query])
