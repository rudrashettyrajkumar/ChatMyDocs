"""Reciprocal Rank Fusion — the multi-query merge (ARCHITECTURE §5.4).

Pure, dependency-free list math: given several ranked result lists (one per Qdrant
search — multiple queries × multiple collections × the dual theme-boost lists), fuse
them into one ranking and return the top-k. No reranker, no model, no I/O (§5.4: the
multi-query+RRF combo captures the recall benefit at zero latency and zero API cost).

The fusion is rank-based, NOT score-based, on purpose: cosine scores from different
collections / filtered-vs-unfiltered searches are not directly comparable, but ranks
always are. A chunk that surfaces in TWO lists (e.g. it appears in both the unfiltered
recall search AND the theme-filtered precision search — the soft-boost mechanism in
METADATA_DESIGN §4) accumulates score from both and naturally outranks a chunk seen in
only one. That is the entire soft-boost trick: no merge code beyond what is here.
"""

from __future__ import annotations

from typing import Any, Protocol

# ARCHITECTURE §5.4 constants. k dampens the contribution of low ranks; top_k is the
# final chunk count handed to the summarizer.
RRF_K = 60
RRF_TOP_K = 6


class _HasId(Protocol):
    """Anything with a stable `id` — a Qdrant ScoredPoint or a test stub."""

    id: Any


def reciprocal_rank_fusion(
    result_lists: list[list[_HasId]],
    k: int = RRF_K,
    top_k: int = RRF_TOP_K,
) -> list[Any]:
    """Fuse ranked lists into one top-k ranking (ARCHITECTURE §5.4 reference).

    ``score[id] += 1 / (k + rank + 1)`` accumulated across every list the chunk
    appears in (rank is 0-based within each list); chunks are de-duplicated by
    ``id``. Ties keep first-seen order (Python sort is stable). Empty lists and
    empty input are fine — an all-empty input returns ``[]``.
    """
    scores: dict[Any, float] = {}
    chunks: dict[Any, Any] = {}
    for results in result_lists:
        for rank, chunk in enumerate(results):
            scores[chunk.id] = scores.get(chunk.id, 0.0) + 1.0 / (k + rank + 1)
            chunks[chunk.id] = chunk
    ranked = sorted(scores, key=lambda cid: scores[cid], reverse=True)
    return [chunks[cid] for cid in ranked[:top_k]]
