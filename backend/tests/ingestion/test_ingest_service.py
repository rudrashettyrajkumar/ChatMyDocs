"""ingest_service tests (spec E2 Required tests): progress event sequence with
mocked embed+qdrant, and rollback-on-failure deleting prior points. `chunk_pages`
is patched to a fixed fake chunk list so these tests are independent of the
chunker's own (separately golden-tested) behavior.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from backend.ingestion.chunker import Chunk
from backend.ingestion.ingest_service import run_ingestion
from backend.utils.embeddings import EmbeddingError

_FAKE_CHUNKS = [
    Chunk(chunk_index=i, text=f"chunk-{i}", page_start=1, page_end=1, token_count=10)
    for i in range(5)
]
_PAGES = [(1, "irrelevant, chunk_pages is mocked"), (2, "irrelevant")]
# doc_id is server-generated via uuid.uuid4() (spec Req 8) — _point_id() requires
# a real UUID to build the deterministic point id, so tests use one too.
_DOC_ID = str(uuid.uuid4())


def _fake_qdrant():
    client = AsyncMock()
    client.upsert = AsyncMock()
    client.delete = AsyncMock()
    return client


async def _collect(agen):
    return [event async for event in agen]


@pytest.fixture(autouse=True)
def _batch_size(monkeypatch):
    """Force 3 embed batches out of 5 fake chunks (2, 2, 1) so the progress
    sequence has more than one embedding event."""
    monkeypatch.setenv("EMBED_BATCH_SIZE", "2")
    from backend.utils.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def test_happy_path_progress_event_sequence():
    qdrant = _fake_qdrant()
    embed_mock = AsyncMock(side_effect=lambda texts, sel=None: [[0.1, 0.2] for _ in texts])

    with (
        patch("backend.ingestion.ingest_service.chunk_pages", return_value=_FAKE_CHUNKS),
        patch("backend.ingestion.ingest_service.get_qdrant", return_value=qdrant),
        patch("backend.ingestion.ingest_service.embed", embed_mock),
    ):
        events = await _collect(
            run_ingestion(_PAGES, doc_id=_DOC_ID, filename="report.pdf", session_id="sess-1")
        )

    assert events == [
        {"stage": "parsing"},
        {"stage": "chunking", "chunks": 5},
        {"stage": "embedding", "pct": 40},
        {"stage": "embedding", "pct": 80},
        {"stage": "embedding", "pct": 100},
        {
            "stage": "ready",
            "doc_id": _DOC_ID,
            "filename": "report.pdf",
            "pages": 2,
            "chunks": 5,
        },
    ]
    assert qdrant.upsert.await_count == 3
    assert qdrant.delete.await_count == 0

    # Spot-check one upserted point's payload matches ARCHITECTURE §5.1 exactly.
    first_call_points = qdrant.upsert.await_args_list[0].kwargs["points"]
    payload = first_call_points[0].payload
    assert payload == {
        "session_id": "sess-1",
        "doc_id": _DOC_ID,
        "filename": "report.pdf",
        "page_start": 1,
        "page_end": 1,
        "chunk_index": 0,
        "text": "chunk-0",
        "created_at": payload["created_at"],  # float timestamp, not asserted exactly
    }
    assert isinstance(payload["created_at"], float)


async def test_mid_embed_failure_rolls_back_and_emits_error():
    qdrant = _fake_qdrant()

    call_count = 0

    async def _embed_fails_second_batch(texts, sel=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return [[0.1, 0.2] for _ in texts]
        raise EmbeddingError("gateway down")  # both the batch call and its one retry

    with (
        patch("backend.ingestion.ingest_service.chunk_pages", return_value=_FAKE_CHUNKS),
        patch("backend.ingestion.ingest_service.get_qdrant", return_value=qdrant),
        patch("backend.ingestion.ingest_service.embed", side_effect=_embed_fails_second_batch),
    ):
        events = await _collect(
            run_ingestion(_PAGES, doc_id=_DOC_ID, filename="report.pdf", session_id="sess-1")
        )

    assert events[:3] == [
        {"stage": "parsing"},
        {"stage": "chunking", "chunks": 5},
        {"stage": "embedding", "pct": 40},
    ]
    assert events[-1]["stage"] == "error"
    assert not any(e["stage"] == "ready" for e in events)

    # First batch's points were upserted; the failure must roll them back.
    assert qdrant.upsert.await_count == 1
    qdrant.delete.assert_awaited_once()
    delete_kwargs = qdrant.delete.await_args.kwargs
    assert delete_kwargs["collection_name"]
    # The rollback filter targets exactly this doc_id.
    condition = delete_kwargs["points_selector"].must[0]
    assert condition.key == "doc_id"
    assert condition.match.value == _DOC_ID

    # Embed was retried exactly once for the failing batch (2 calls: first fail + retry).
    assert call_count == 3  # batch 1 (ok) + batch 2 (fail) + batch 2 retry (fail)


async def test_upsert_failure_rolls_back_and_emits_error():
    qdrant = _fake_qdrant()
    qdrant.upsert = AsyncMock(side_effect=[None, RuntimeError("qdrant unavailable")])
    embed_mock = AsyncMock(side_effect=lambda texts, sel=None: [[0.1, 0.2] for _ in texts])

    with (
        patch("backend.ingestion.ingest_service.chunk_pages", return_value=_FAKE_CHUNKS),
        patch("backend.ingestion.ingest_service.get_qdrant", return_value=qdrant),
        patch("backend.ingestion.ingest_service.embed", embed_mock),
    ):
        events = await _collect(
            run_ingestion(_PAGES, doc_id=_DOC_ID, filename="report.pdf", session_id="sess-1")
        )

    assert events[-1]["stage"] == "error"
    assert not any(e["stage"] == "ready" for e in events)
    qdrant.delete.assert_awaited_once()
