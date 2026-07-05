"""retrieval_agent tests (spec E3 Required tests): mocked embed+Qdrant — the
session filter is ALWAYS present on every search call, partial-failure
degradation, the low_relevance flag, and stable citation numbering.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from backend.agents.retrieval_agent import retrieve
from backend.utils.embeddings import EmbeddingError

_SESSION_ID = "session-a"


def _point(id_: str, score: float, **payload) -> SimpleNamespace:
    base = {
        "session_id": _SESSION_ID,
        "doc_id": "doc-1",
        "filename": "report.pdf",
        "page_start": 1,
        "page_end": 1,
        "chunk_index": 0,
        "text": "some chunk text",
    }
    base.update(payload)
    return SimpleNamespace(id=id_, score=score, payload=base)


def _fake_qdrant(search_mock: AsyncMock) -> SimpleNamespace:
    return SimpleNamespace(search=search_mock)


async def test_session_filter_always_present_on_every_search_call():
    search_mock = AsyncMock(
        side_effect=[[_point("a", 0.9)], [_point("b", 0.8)]]
    )
    with (
        patch(
            "backend.agents.retrieval_agent.embed",
            AsyncMock(return_value=[[0.1, 0.2], [0.3, 0.4]]),
        ),
        patch(
            "backend.agents.retrieval_agent.get_qdrant",
            return_value=_fake_qdrant(search_mock),
        ),
    ):
        await retrieve(["query one", "query two"], session_id=_SESSION_ID)

    assert search_mock.await_count == 2
    for call in search_mock.await_args_list:
        query_filter = call.kwargs["query_filter"]
        condition = query_filter.must[0]
        assert condition.key == "session_id"
        assert condition.match.value == _SESSION_ID


async def test_partial_search_failure_degrades_to_remaining_results():
    search_mock = AsyncMock(
        side_effect=[RuntimeError("qdrant unavailable"), [_point("b", 0.9)]]
    )
    with (
        patch(
            "backend.agents.retrieval_agent.embed",
            AsyncMock(return_value=[[0.1, 0.2], [0.3, 0.4]]),
        ),
        patch(
            "backend.agents.retrieval_agent.get_qdrant",
            return_value=_fake_qdrant(search_mock),
        ),
    ):
        result = await retrieve(["query one", "query two"], session_id=_SESSION_ID)

    assert [c.id for c in result.chunks] == ["b"]
    assert result.low_relevance is False


async def test_all_searches_failing_degrades_to_empty_with_low_relevance():
    search_mock = AsyncMock(side_effect=RuntimeError("qdrant unavailable"))
    with (
        patch(
            "backend.agents.retrieval_agent.embed",
            AsyncMock(return_value=[[0.1, 0.2]]),
        ),
        patch(
            "backend.agents.retrieval_agent.get_qdrant",
            return_value=_fake_qdrant(search_mock),
        ),
    ):
        result = await retrieve(["query one"], session_id=_SESSION_ID)

    assert result.chunks == []
    assert result.low_relevance is True


async def test_embed_failure_degrades_to_empty_with_low_relevance():
    with patch(
        "backend.agents.retrieval_agent.embed",
        AsyncMock(side_effect=EmbeddingError("gateway down")),
    ):
        result = await retrieve(["query one"], session_id=_SESSION_ID)

    assert result.chunks == []
    assert result.low_relevance is True


async def test_no_queries_short_circuits_to_empty():
    result = await retrieve([], session_id=_SESSION_ID)
    assert result.chunks == []
    assert result.low_relevance is True


async def test_low_relevance_flag_reflects_best_score_vs_threshold(monkeypatch):
    monkeypatch.setenv("RELEVANCE_THRESHOLD", "0.5")
    from backend.utils.config import get_settings

    get_settings.cache_clear()
    search_mock = AsyncMock(return_value=[_point("a", 0.2)])
    with (
        patch("backend.agents.retrieval_agent.embed", AsyncMock(return_value=[[0.1]])),
        patch(
            "backend.agents.retrieval_agent.get_qdrant",
            return_value=_fake_qdrant(search_mock),
        ),
    ):
        result = await retrieve(["low relevance query"], session_id=_SESSION_ID)
    get_settings.cache_clear()

    assert result.low_relevance is True


async def test_citation_numbering_stable_and_labels_span_pages():
    search_mock = AsyncMock(
        return_value=[
            _point("a", 0.9, filename="report.pdf", page_start=3, page_end=3),
            _point("b", 0.8, filename="report.pdf", page_start=5, page_end=6),
        ]
    )
    with (
        patch("backend.agents.retrieval_agent.embed", AsyncMock(return_value=[[0.1]])),
        patch(
            "backend.agents.retrieval_agent.get_qdrant",
            return_value=_fake_qdrant(search_mock),
        ),
    ):
        result = await retrieve(["query"], session_id=_SESSION_ID)

    assert [c.n for c in result.chunks] == [1, 2]
    assert result.chunks[0].citation_label == "report.pdf, p.3"
    assert result.chunks[1].citation_label == "report.pdf, p.5–6"
