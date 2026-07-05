"""Token-aware chunking with page tracking (ARCHITECTURE §5.2, spec E2 Req 3).

CHUNK_TOKENS/CHUNK_OVERLAP (config.py) are counted with tiktoken's `cl100k_base`
— the same tokenizer family the embedding/answer models roughly approximate,
so a "450-token chunk" means something consistent regardless of which model
ends up reading it. Packing prefers whole paragraphs; a paragraph that alone
exceeds the budget is hard-split on raw token boundaries (not sentence-safe —
that's the "hard" in hard-split, reserved for the rare oversized paragraph).

Page numbers are tracked per PARAGRAPH UNIT, not per chunk, so a chunk's
`page_start`/`page_end` is always the true min/max page of whatever text it
actually contains — including the carried-over overlap tail from the previous
chunk, which is how a chunk can legitimately span a page break (spec Req 3).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from backend.utils.config import get_settings

# A run of 2+ newlines is a paragraph break; a single newline inside a
# paragraph is just a PDF line-wrap and is folded to a space so chunk text
# reads as continuous prose (data-driven choice — PyMuPDF's plain-text mode
# does not reliably mark hard line breaks otherwise).
_PARAGRAPH_BOUNDARY = re.compile(r"\n\s*\n")
_INTRALINE_BREAK = re.compile(r"\s*\n\s*")


@lru_cache(maxsize=1)
def _encoding():
    import tiktoken

    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """`cl100k_base` token count of `text` — the single counting method shared
    by chunking and any caller that needs to reason about chunk size."""
    return len(_encoding().encode(text))


@dataclass(frozen=True)
class Chunk:
    chunk_index: int
    text: str
    page_start: int
    page_end: int
    token_count: int


@dataclass(frozen=True)
class _Unit:
    """One packable span of text tied to the single page it came from."""

    text: str
    page: int
    tokens: int


def _paragraphs(page_no: int, text: str) -> list[_Unit]:
    """A page's text split into paragraph units (blank lines removed, each
    unit's internal line-wraps folded to spaces)."""
    units: list[_Unit] = []
    for para in _PARAGRAPH_BOUNDARY.split(text):
        cleaned = _INTRALINE_BREAK.sub(" ", para).strip()
        if cleaned:
            units.append(_Unit(text=cleaned, page=page_no, tokens=count_tokens(cleaned)))
    return units


def _hard_split(unit: _Unit, budget: int) -> list[_Unit]:
    """Cut an oversized paragraph into `budget`-token windows, raw token
    boundaries (no sentence awareness — spec Req 3's "hard-split")."""
    enc = _encoding()
    tokens = enc.encode(unit.text)
    pieces: list[_Unit] = []
    for start in range(0, len(tokens), budget):
        window = tokens[start : start + budget]
        pieces.append(_Unit(text=enc.decode(window), page=unit.page, tokens=len(window)))
    return pieces


def _units_for_pages(pages: list[tuple[int, str]], budget: int) -> list[_Unit]:
    units: list[_Unit] = []
    for page_no, text in pages:
        for para in _paragraphs(page_no, text):
            units.extend(_hard_split(para, budget) if para.tokens > budget else [para])
    return units


def _overlap_tail(units: list[_Unit], overlap_tokens: int) -> list[_Unit]:
    """The trailing units of a just-emitted chunk, ~`overlap_tokens` worth,
    carried into the next chunk for continuity (ARCHITECTURE §5.2)."""
    tail: list[_Unit] = []
    total = 0
    for unit in reversed(units):
        if total >= overlap_tokens:
            break
        tail.insert(0, unit)
        total += unit.tokens
    return tail


def _finalize(units: list[_Unit], chunk_index: int) -> Chunk:
    return Chunk(
        chunk_index=chunk_index,
        text="\n\n".join(u.text for u in units),
        page_start=min(u.page for u in units),
        page_end=max(u.page for u in units),
        token_count=sum(u.tokens for u in units),
    )


def chunk_pages(pages: list[tuple[int, str]]) -> list[Chunk]:
    """Pack `[(page_no, text), ...]` into ~`CHUNK_TOKENS`-token chunks with
    `CHUNK_OVERLAP` overlap (ARCHITECTURE §5.2), tracking page numbers through
    every split and overlap so citations stay honest — including chunks that
    straddle a page break.
    """
    settings = get_settings()
    budget = settings.CHUNK_TOKENS
    overlap = settings.CHUNK_OVERLAP

    units = _units_for_pages(pages, budget)
    if not units:
        return []

    chunks: list[Chunk] = []
    current: list[_Unit] = []
    current_tokens = 0
    for unit in units:
        if current and current_tokens + unit.tokens > budget:
            chunks.append(_finalize(current, len(chunks)))
            current = _overlap_tail(current, overlap)
            current_tokens = sum(u.tokens for u in current)
        current.append(unit)
        current_tokens += unit.tokens
    if current:
        chunks.append(_finalize(current, len(chunks)))
    return chunks
