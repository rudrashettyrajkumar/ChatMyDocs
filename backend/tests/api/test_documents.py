"""`/documents` API tests (spec E2 Required tests): all four pre-stream
rejection cases, the happy-path upload→list→delete lifecycle, and the
ownership check on DELETE. Redis and Qdrant are faked in-memory so state
(session doc counts, persisted metadata) behaves realistically across calls
within a test, without hitting real services.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock

import pytest

from backend.tests.conftest import bearer
from backend.utils.redis_client import dc_key


def _make_pdf(pages_text: list[str]) -> bytes:
    """A real, in-memory PDF — one page per string (empty = blank/no text)."""
    import fitz

    doc = fitz.open()
    for text in pages_text:
        page = doc.new_page()
        if text:
            margin = 36
            rect = fitz.Rect(margin, margin, page.rect.width - margin, page.rect.height - margin)
            page.insert_textbox(rect, text)
    data = doc.tobytes()
    doc.close()
    return data


def _parse_sse(text: str) -> list[dict]:
    lines = (line for line in text.splitlines() if line.startswith("data: "))
    return [json.loads(line[len("data: ") :]) for line in lines]


class FakeRedis:
    """In-memory stand-in for `UpstashRedis` — real enough (hashes, sets,
    counters) that session/doc state behaves consistently across calls."""

    def __init__(self) -> None:
        self.hashes: dict[str, dict[str, str]] = {}
        self.sets: dict[str, set[str]] = {}
        self.counters: dict[str, int] = {}

    async def smembers(self, key):
        return list(self.sets.get(key, set()))

    async def sadd(self, key, *values):
        self.sets.setdefault(key, set()).update(str(v) for v in values)
        return len(values)

    async def srem(self, key, *values):
        bucket = self.sets.get(key, set())
        removed = 0
        for v in values:
            if str(v) in bucket:
                bucket.discard(str(v))
                removed += 1
        return removed

    async def hset(self, key, mapping):
        self.hashes.setdefault(key, {}).update({k: str(v) for k, v in mapping.items()})
        return len(mapping)

    async def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    async def delete(self, key):
        existed = key in self.hashes or key in self.sets
        self.hashes.pop(key, None)
        self.sets.pop(key, None)
        return 1 if existed else 0

    async def incr(self, key):
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    async def expire(self, key, seconds):
        return 1

    async def pipeline(self, *commands):
        results = []
        for name, key, *args in commands:
            if name == "HSET":
                results.append(await self.hset(key, dict(zip(args[0::2], args[1::2], strict=True))))
            elif name == "EXPIRE":
                results.append(await self.expire(key, args[0]))
            elif name == "SADD":
                results.append(await self.sadd(key, *args))
            else:
                raise AssertionError(f"unexpected pipeline command: {name}")
        return results


@pytest.fixture
def fake_redis(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr("backend.api.documents.get_redis", lambda: redis)
    monkeypatch.setattr("backend.middleware.rate_limit.get_redis", lambda: redis)
    return redis


@pytest.fixture
def fake_qdrant(monkeypatch):
    qdrant = AsyncMock()
    monkeypatch.setattr("backend.api.documents.get_qdrant", lambda: qdrant)
    monkeypatch.setattr("backend.ingestion.ingest_service.get_qdrant", lambda: qdrant)
    return qdrant


@pytest.fixture(autouse=True)
def fake_embed(monkeypatch):
    embed_mock = AsyncMock(side_effect=lambda texts, sel=None: [[0.1, 0.2] for _ in texts])
    monkeypatch.setattr("backend.ingestion.ingest_service.embed", embed_mock)
    return embed_mock


def _sid() -> str:
    return str(uuid.uuid4())


def _upload(client, data: bytes, *, session_id: str | None = None, filename: str = "doc.pdf"):
    return client.post(
        "/documents",
        headers=bearer(session_id),
        files={"file": (filename, data, "application/pdf")},
    )


# --------------------------------------------------------------------- rejections


def test_rejects_non_pdf_file(client, fake_redis, fake_qdrant):
    resp = _upload(client, b"just a text file, not a pdf", filename="notes.txt")
    assert resp.status_code == 400
    assert resp.json() == {"error": "invalid_file", "detail": resp.json()["detail"]}


def test_rejects_oversized_file(client, fake_redis, fake_qdrant):
    oversized = b"%PDF-1.4\n" + b"0" * (11 * 1024 * 1024)  # over the 10MB default
    resp = _upload(client, oversized)
    assert resp.status_code == 413
    assert resp.json()["error"] == "file_too_large"


def test_rejects_fourth_document_in_session(client, fake_redis, fake_qdrant):
    sid = _sid()
    # Already at MAX_DOCS_PER_SESSION.
    fake_redis.sets[dc_key("session", sid, "docs")] = {"d1", "d2", "d3"}
    pdf = _make_pdf(["Some real extractable text content. " * 10])
    resp = _upload(client, pdf, session_id=sid)
    assert resp.status_code == 400
    assert resp.json()["error"] == "too_many_documents"


def test_rejects_scanned_pdf(client, fake_redis, fake_qdrant):
    scanned = _make_pdf(["", ""])  # blank pages, no extractable text
    resp = _upload(client, scanned)
    assert resp.status_code == 422
    assert resp.json()["error"] == "scanned_pdf"


def test_four_rejections_are_distinct_error_codes(client, fake_redis, fake_qdrant):
    sid = _sid()
    fake_redis.sets[dc_key("session", sid, "docs")] = {"d1", "d2", "d3"}
    codes = {
        _upload(client, b"not a pdf", filename="x.txt").json()["error"],
        _upload(client, b"%PDF-1.4\n" + b"0" * (11 * 1024 * 1024)).json()["error"],
        _upload(client, _make_pdf(["Some real content. " * 10]), session_id=sid).json()["error"],
        _upload(client, _make_pdf(["", ""])).json()["error"],
    }
    assert codes == {"invalid_file", "file_too_large", "too_many_documents", "scanned_pdf"}


# --------------------------------------------------------------------- happy path


def test_upload_streams_progress_and_lands_in_list_then_delete(client, fake_redis, fake_qdrant):
    sid = _sid()
    pdf = _make_pdf(["Page one has real extractable text content here. " * 5,
                      "Page two also has real extractable text content. " * 5])

    resp = _upload(client, pdf, session_id=sid, filename="../../etc/report.pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(resp.text)
    assert events[0] == {"stage": "parsing"}
    assert events[1]["stage"] == "chunking"
    ready = events[-1]
    assert ready["stage"] == "ready"
    assert ready["pages"] == 2
    assert ready["filename"] == "report.pdf"  # path components stripped (spec Req 8)
    doc_id = ready["doc_id"]

    listed = client.get("/documents", headers=bearer(sid)).json()
    assert len(listed) == 1
    assert listed[0]["doc_id"] == doc_id
    assert listed[0]["pages"] == 2
    assert listed[0]["filename"] == "report.pdf"

    delete_resp = client.delete(f"/documents/{doc_id}", headers=bearer(sid))
    assert delete_resp.status_code == 200
    assert delete_resp.json() == {"deleted": True}
    fake_qdrant.delete.assert_awaited_once()

    assert client.get("/documents", headers=bearer(sid)).json() == []


def test_demo_embedding_failure_gets_free_tier_error(client, fake_redis, fake_qdrant, fake_embed):
    """No BYOK headers + embedding down → the SSE error names the free tier and
    the bring-your-own-key fix, never the raw provider error."""
    from backend.utils.embeddings import EmbeddingError

    fake_embed.side_effect = EmbeddingError("429 too many requests")
    pdf = _make_pdf(["Real extractable text content on this page. " * 5])

    resp = _upload(client, pdf, session_id=_sid())
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    error = events[-1]
    assert error["stage"] == "error"
    assert "free-tier" in error["detail"]
    assert "own embedding key" in error["detail"]
    assert "429" not in error["detail"]


def test_sample_pdf_ingests_with_correct_page_payloads(client, fake_redis, fake_qdrant):
    """Acceptance criteria: uploading `sample/sample.pdf` lands N chunks with
    correct, monotonically sane page payloads (spot-checked here since Qdrant
    itself is mocked)."""
    from pathlib import Path

    pdf_path = Path(__file__).resolve().parents[3] / "sample" / "sample.pdf"
    pdf_bytes = pdf_path.read_bytes()

    resp = _upload(client, pdf_bytes, filename="sample.pdf")
    assert resp.status_code == 200
    ready = _parse_sse(resp.text)[-1]
    assert ready["stage"] == "ready"
    assert 10 <= ready["pages"] <= 30
    assert ready["chunks"] > 0

    all_points = [pt for call in fake_qdrant.upsert.await_args_list for pt in call.kwargs["points"]]
    assert len(all_points) == ready["chunks"]
    assert len({pt.id for pt in all_points}) == len(all_points)  # no duplicate point ids
    for pt in all_points:
        assert 1 <= pt.payload["page_start"] <= pt.payload["page_end"] <= ready["pages"]
    # chunk_index is sequential and covers the full range with no gaps.
    indices = sorted(pt.payload["chunk_index"] for pt in all_points)
    assert indices == list(range(len(all_points)))


def test_delete_ownership_check_cross_session(client, fake_redis, fake_qdrant):
    owner_sid, other_sid = _sid(), _sid()
    doc_id = str(uuid.uuid4())
    fake_redis.hashes[dc_key("doc", doc_id)] = {
        "filename": "secret.pdf",
        "pages": "3",
        "chunks": "5",
        "session_id": owner_sid,
        "created_at": "123.0",
    }
    fake_redis.sets[dc_key("session", owner_sid, "docs")] = {doc_id}

    resp = client.delete(f"/documents/{doc_id}", headers=bearer(other_sid))
    assert resp.status_code == 404
    fake_qdrant.delete.assert_not_awaited()

    # The rightful owner can still delete it.
    resp = client.delete(f"/documents/{doc_id}", headers=bearer(owner_sid))
    assert resp.status_code == 200


def test_list_degrades_to_empty_on_redis_outage(client, monkeypatch):
    broken_redis = AsyncMock()
    broken_redis.smembers = AsyncMock(side_effect=ConnectionError("redis unreachable"))
    monkeypatch.setattr("backend.api.documents.get_redis", lambda: broken_redis)

    resp = client.get("/documents", headers=bearer())
    assert resp.status_code == 200
    assert resp.json() == []


def test_delete_returns_503_not_500_on_redis_outage(client, monkeypatch):
    broken_redis = AsyncMock()
    broken_redis.hgetall = AsyncMock(side_effect=ConnectionError("redis unreachable"))
    monkeypatch.setattr("backend.api.documents.get_redis", lambda: broken_redis)

    resp = client.delete(f"/documents/{uuid.uuid4()}", headers=bearer())
    assert resp.status_code == 503
