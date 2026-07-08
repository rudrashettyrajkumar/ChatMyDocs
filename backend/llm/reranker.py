"""Optional open-source rerank stage — FlashRank cross-encoder, degrade-to-noop.

RRF fusion ranks by agreement across query variants; a cross-encoder then
re-scores each candidate against the ORIGINAL question, which is much better
at kicking out topically-adjacent-but-useless chunks. FlashRank's default
model (`ms-marco-TinyBERT-L-2-v2`, ~4 MB ONNX, CPU) keeps the container far
from anything torch-sized.

Everything degrades: flashrank not installed, model download blocked, scoring
crash — all fall back to the RRF order (logged once), because a slightly
worse ranking beats a broken chat turn. Scoring is sync CPU work, so it runs
in a worker thread off the event loop.

Chunks are re-numbered after reranking so citation `[n]` stays 1..k in rank
order — prompt_assembly and the sources SSE event key off `chunk.n`.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from backend.utils.config import get_settings

if TYPE_CHECKING:
    from backend.agents.retrieval_agent import RetrievedChunk

_log = logging.getLogger("docchat.reranker")

_ranker: Any = None
_ranker_failed = False  # remember a failed init; don't retry every turn


def _get_ranker() -> Any:
    """Lazily build the FlashRank ranker; None when unavailable (degrade)."""
    global _ranker, _ranker_failed
    if _ranker is not None or _ranker_failed:
        return _ranker
    try:
        from flashrank import Ranker

        _ranker = Ranker(max_length=512)  # default tiny model, downloaded once
    except Exception as exc:  # noqa: BLE001 — missing dep/model is a degrade, not a break
        _ranker_failed = True
        _log.warning("flashrank unavailable; rerank disabled", extra={"reason": repr(exc)})
    return _ranker


def _score(question: str, chunks: list[RetrievedChunk]) -> list[tuple[int, float]]:
    """Sync FlashRank scoring → [(chunk_list_index, score)], best first."""
    from flashrank import RerankRequest

    passages = [{"id": i, "text": chunk.text} for i, chunk in enumerate(chunks)]
    results = _ranker.rerank(RerankRequest(query=question, passages=passages))
    return [(int(r["id"]), float(r["score"])) for r in results]


def _renumber(ordered: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """Re-assign citation numbers 1..k in the new rank order."""
    return [replace(chunk, n=i) for i, chunk in enumerate(ordered, start=1)]


async def rerank(question: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """Top `RERANK_TOP_K` chunks for `question`, cross-encoder ordered.

    Never raises. Disabled/unavailable reranker → the RRF order, truncated to
    the same top-k the answerer would otherwise see.
    """
    settings = get_settings()
    top_k = settings.RERANK_TOP_K
    if not chunks:
        return chunks
    if not settings.RERANK_ENABLED or _get_ranker() is None:
        return _renumber(chunks[:top_k])
    try:
        scored = await asyncio.to_thread(_score, question, chunks)
    except Exception as exc:  # noqa: BLE001 — scoring failure degrades to RRF order
        _log.warning("rerank failed; keeping RRF order", extra={"error": repr(exc)})
        return _renumber(chunks[:top_k])
    ordered = [chunks[i] for i, _ in scored[:top_k]]
    return _renumber(ordered)
