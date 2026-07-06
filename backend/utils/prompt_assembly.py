"""Prompt assembly — the answerer's system + user turn (ARCHITECTURE §6, spec E4 Req 2).

System = `answerer_identity.md` + `citation_rules.md`, concatenated once and cached.
User turn = three labeled blocks in a FIXED order: `[CONTEXT]` (numbered,
citation-labeled chunks), `[HISTORY]` (last 6 turns), `[QUESTION]`. These three
bracketed labels are also `guardrails.guard_stream`'s leak signature (E1) — the
answerer must never see them spelled any other way.

Prompts are `.md` files, never Python strings (CLAUDE.md invariant 6); this module
only composes the blocks around them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.agents.retrieval_agent import RetrievedChunk

_PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
# Same short-term window as rewrite_agent (ARCHITECTURE §3.2) — history is stored
# with more turns (LTRIM 12) but only the last 6 are shown to any model.
_HISTORY_TURNS = 6

_SYSTEM_CACHE: str | None = None
_NO_DOCS_CACHE: str | None = None


def _read(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


def system_prompt() -> str:
    """Lazily-cached system prompt: identity + citation rules, in that order (§6)."""
    global _SYSTEM_CACHE
    if _SYSTEM_CACHE is None:
        _SYSTEM_CACHE = f"{_read('answerer_identity.md')}\n\n{_read('citation_rules.md')}"
    return _SYSTEM_CACHE


def no_docs_message() -> str:
    """Lazily-cached canned reply for the zero-documents pipeline exit (§3.2 step 1)."""
    global _NO_DOCS_CACHE
    if _NO_DOCS_CACHE is None:
        _NO_DOCS_CACHE = _read("no_docs.md")
    return _NO_DOCS_CACHE


def _format_context(chunks: list[RetrievedChunk], low_relevance: bool) -> str:
    if not chunks:
        return "(no relevant document content found)"
    body = "\n\n".join(f"[{c.n}] {c.citation_label}\n{c.text}" for c in chunks)
    if low_relevance:
        return f"(marked low relevance — this material may not answer the question)\n\n{body}"
    return body


def _format_history(history: list[dict[str, Any]]) -> str:
    turns = history[-_HISTORY_TURNS:]
    lines: list[str] = []
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        role = str(turn.get("role", "user")).strip() or "user"
        content = str(turn.get("content", "")).strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines) if lines else "(no prior turns)"


def user_turn(
    chunks: list[RetrievedChunk], history: list[dict[str, Any]], question: str, low_relevance: bool
) -> str:
    """Assemble `[CONTEXT]` + `[HISTORY]` + `[QUESTION]` in that fixed order (§6)."""
    return (
        f"[CONTEXT]\n{_format_context(chunks, low_relevance)}\n\n"
        f"[HISTORY]\n{_format_history(history)}\n\n"
        f"[QUESTION]\n{question}"
    )


def build_messages(
    chunks: list[RetrievedChunk],
    history: list[dict[str, Any]],
    question: str,
    low_relevance: bool,
) -> list[dict[str, str]]:
    """The full `answerer` chat-completion messages list."""
    return [
        {"role": "system", "content": system_prompt()},
        {"role": "user", "content": user_turn(chunks, history, question, low_relevance)},
    ]
