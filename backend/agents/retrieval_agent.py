"""Retrieval agent — multi-query embed + session-filtered Qdrant + RRF fusion.

ARCHITECTURE §3.2 step 4 / §5.3-5.4, spec E3 Req 2-5. Takes the rewrite
agent's standalone queries, embeds all of them in ONE batched call, runs a
session-filtered Qdrant search per query in parallel, fuses the ranked lists
with `utils.rrf.reciprocal_rank_fusion`, and returns the top 6 chunks
numbered and labeled for citation.

The `session_id` payload filter is built in exactly ONE place in this module
(`_search_one`) — call sites never construct their own filter (qdrant-rag
skill / CLAUDE.md invariant 2, ARCHITECTURE §5.1). A test asserts the filter
is present on every search call.

Errors degrade, never break (spec Req 5): the embed call failing takes down
the whole batch (it is a single request for all queries), so it degrades to
empty chunks + low_relevance; a single query's Qdrant SEARCH failing degrades
to proceeding with whichever queries succeeded; every search failing also
degrades to empty chunks + low_relevance. This agent never raises.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from backend.utils.config import get_settings
from backend.utils.embeddings import EmbeddingError, embed
from backend.utils.qdrant_client import get_qdrant
from backend.utils.rrf import reciprocal_rank_fusion

_log = logging.getLogger("docchat.retrieval_agent")

# Per-query candidate pool before fusion (ARCHITECTURE §5.3: "top-8 per query").
_SEARCH_LIMIT_PER_QUERY = 8


@dataclass(frozen=True)
class RetrievedChunk:
    """One fused, citation-numbered chunk (spec Req 3)."""

    n: int  # 1-based citation number, stable across the fused ranking
    id: str
    doc_id: str
    filename: str
    page_start: int
    page_end: int
    text: str
    score: float
    citation_label: str


@dataclass(frozen=True)
class RetrievalResult:
    chunks: list[RetrievedChunk]
    low_relevance: bool


# Shared degraded-path result (spec Req 5: never an exception out of the agent).
_EMPTY_RESULT = RetrievalResult(chunks=[], low_relevance=True)


def _citation_label(filename: str, page_start: int, page_end: int) -> str:
    """`"{filename}, p.{page_start}"`, or a `p.{start}-{end}` range when the
    chunk spans pages (spec Req 3)."""
    if page_start == page_end:
        return f"{filename}, p.{page_start}"
    return f"{filename}, p.{page_start}–{page_end}"


async def _search_one(vector: list[float], session_id: str, collection: str) -> list[Any]:
    """The ONE place the mandatory session_id filter is built (invariant 2)."""
    from qdrant_client import models

    return await get_qdrant().search(
        collection_name=collection,
        query_vector=vector,
        query_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="session_id", match=models.MatchValue(value=session_id)
                )
            ]
        ),
        limit=_SEARCH_LIMIT_PER_QUERY,
    )


async def _search_all(
    vectors: list[list[float]], session_id: str, collection: str
) -> list[list[Any]]:
    """Run one filtered search per query vector in parallel.

    A failing search is logged and dropped, not propagated (spec Req 5:
    partial failure degrades to whatever succeeded).
    """
    results = await asyncio.gather(
        *(_search_one(vector, session_id, collection) for vector in vectors),
        return_exceptions=True,
    )
    lists: list[list[Any]] = []
    for result in results:
        if isinstance(result, Exception):
            _log.warning("qdrant search failed; degrading", extra={"error": str(result)})
            continue
        lists.append(result)
    return lists


def _to_chunk(point: Any, n: int) -> RetrievedChunk:
    payload = point.payload or {}
    filename = payload.get("filename", "")
    page_start = payload.get("page_start", 0)
    page_end = payload.get("page_end", 0)
    return RetrievedChunk(
        n=n,
        id=str(point.id),
        doc_id=payload.get("doc_id", ""),
        filename=filename,
        page_start=page_start,
        page_end=page_end,
        text=payload.get("text", ""),
        score=point.score,
        citation_label=_citation_label(filename, page_start, page_end),
    )


async def retrieve(queries: list[str], session_id: str) -> RetrievalResult:
    """Embed `queries`, search Qdrant filtered to `session_id`, fuse, and label.

    Never raises: any failure degrades to `RetrievalResult([], low_relevance=True)`.
    """
    if not queries:
        return _EMPTY_RESULT

    settings = get_settings()
    try:
        vectors = await embed(queries)
    except EmbeddingError as exc:
        _log.warning("query embedding failed; degrading", extra={"error": str(exc)})
        return _EMPTY_RESULT

    result_lists = await _search_all(vectors, session_id, settings.QDRANT_COLLECTION)
    if not result_lists:
        return _EMPTY_RESULT

    fused = reciprocal_rank_fusion(result_lists)
    if not fused:
        return _EMPTY_RESULT

    best_score = max(point.score for point in fused)
    low_relevance = best_score < settings.RELEVANCE_THRESHOLD

    chunks = [_to_chunk(point, n) for n, point in enumerate(fused, start=1)]
    return RetrievalResult(chunks=chunks, low_relevance=low_relevance)
