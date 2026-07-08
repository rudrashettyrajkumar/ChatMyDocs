"""Reranker degrade paths: unavailable/disabled → RRF order truncated and
RE-NUMBERED (citation [n] must stay 1..k), and scored order wins when present."""

from unittest.mock import patch

from backend.agents.retrieval_agent import RetrievedChunk
from backend.llm import reranker


def _chunk(n: int) -> RetrievedChunk:
    return RetrievedChunk(
        n=n,
        id=f"pt-{n}",
        doc_id="doc-1",
        filename="report.pdf",
        page_start=n,
        page_end=n,
        text=f"chunk {n}",
        score=1.0 / n,
        citation_label=f"report.pdf, p.{n}",
    )


_POOL = [_chunk(i) for i in range(1, 9)]  # 8 fused candidates


async def test_unavailable_ranker_degrades_to_rrf_order_top_k():
    with patch.object(reranker, "_get_ranker", return_value=None):
        out = await reranker.rerank("question", _POOL)
    assert [c.text for c in out] == [f"chunk {i}" for i in range(1, 7)]  # RRF order, top 6
    assert [c.n for c in out] == [1, 2, 3, 4, 5, 6]


async def test_disabled_via_env_degrades_the_same_way(monkeypatch):
    monkeypatch.setenv("RERANK_ENABLED", "false")
    from backend.utils.config import get_settings

    get_settings.cache_clear()
    out = await reranker.rerank("question", _POOL)
    assert len(out) == 6
    assert [c.n for c in out] == [1, 2, 3, 4, 5, 6]


async def test_scored_order_wins_and_chunks_are_renumbered():
    # Fake scorer: reverse the pool → chunk 8 becomes citation [1].
    scored = [(i, float(10 - i)) for i in reversed(range(len(_POOL)))]
    with (
        patch.object(reranker, "_get_ranker", return_value=object()),
        patch.object(reranker, "_score", return_value=scored),
    ):
        out = await reranker.rerank("question", _POOL)
    assert [c.text for c in out] == [f"chunk {i}" for i in range(8, 2, -1)]
    assert [c.n for c in out] == [1, 2, 3, 4, 5, 6]  # renumbered in new order


async def test_scoring_crash_degrades_to_rrf_order():
    with (
        patch.object(reranker, "_get_ranker", return_value=object()),
        patch.object(reranker, "_score", side_effect=RuntimeError("onnx exploded")),
    ):
        out = await reranker.rerank("question", _POOL)
    assert [c.n for c in out] == [1, 2, 3, 4, 5, 6]


async def test_empty_chunks_pass_through():
    assert await reranker.rerank("q", []) == []
