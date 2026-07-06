"""Answer agent: seq monotonicity (via the caller), cited-source flags computed
from answer text, and mid-stream failure propagation (spec E4 required tests)."""

from unittest.mock import patch

import pytest

from backend.agents.answer_agent import cited_sources, stream_answer
from backend.agents.retrieval_agent import RetrievedChunk
from backend.utils.guardrails import GuardrailTripped

_CHUNKS = [
    RetrievedChunk(
        n=1,
        id="pt-1",
        doc_id="doc-1",
        filename="report.pdf",
        page_start=3,
        page_end=3,
        text="Revenue grew 12% year over year, driven by strong demand.",
        score=0.81,
        citation_label="report.pdf, p.3",
    ),
    RetrievedChunk(
        n=2,
        id="pt-2",
        doc_id="doc-1",
        filename="report.pdf",
        page_start=5,
        page_end=6,
        text="Risk factors include supply chain volatility.",
        score=0.40,
        citation_label="report.pdf, p.5–6",
    ),
]


def test_cited_sources_flags_only_numbers_present_in_answer_text():
    sources = cited_sources(_CHUNKS, "Revenue grew 12% [1]. Other risks were not discussed.")
    by_n = {s["n"]: s for s in sources}
    assert by_n[1]["cited"] is True
    assert by_n[2]["cited"] is False


def test_cited_sources_shapes_pages_and_snippet():
    sources = cited_sources(_CHUNKS, "[1][2]")
    by_n = {s["n"]: s for s in sources}
    assert by_n[1]["pages"] == "3"
    assert by_n[2]["pages"] == "5-6"
    assert by_n[1]["snippet"] == _CHUNKS[0].text
    assert by_n[1]["doc_id"] == "doc-1"
    assert by_n[1]["filename"] == "report.pdf"
    assert by_n[1]["score"] == 0.81


def test_cited_sources_snippet_truncated_to_300_chars():
    long_chunk = RetrievedChunk(
        n=1,
        id="pt-x",
        doc_id="doc-1",
        filename="x.pdf",
        page_start=1,
        page_end=1,
        text="a" * 500,
        score=0.9,
        citation_label="x.pdf, p.1",
    )
    sources = cited_sources([long_chunk], "[1]")
    assert len(sources[0]["snippet"]) == 300


async def _fake_tokens(*parts: str):
    for part in parts:
        yield part


async def test_stream_answer_yields_router_tokens_through_guard():
    with patch(
        "backend.agents.answer_agent.llm_router.stream",
        return_value=_fake_tokens("The ", "answer ", "is ", "42 [1]."),
    ) as mock_stream:
        out = [tok async for tok in stream_answer(_CHUNKS, [], "what is it?", False)]
    assert "".join(out) == "The answer is 42 [1]."
    assert mock_stream.call_args.args[0] == "answerer"


async def test_stream_answer_propagates_router_failure():
    async def _boom(*_a, **_kw):
        raise TimeoutError("provider timeout")
        yield  # pragma: no cover - makes this an async generator function

    with patch("backend.agents.answer_agent.llm_router.stream", side_effect=_boom):
        with pytest.raises(TimeoutError):
            async for _ in stream_answer(_CHUNKS, [], "q", False):
                pass


async def test_stream_answer_propagates_guardrail_trip_on_leaked_marker():
    with patch(
        "backend.agents.answer_agent.llm_router.stream",
        return_value=_fake_tokens("safe start ", "[CONTEXT] leaking"),
    ):
        with pytest.raises(GuardrailTripped):
            async for _ in stream_answer(_CHUNKS, [], "q", False):
                pass
