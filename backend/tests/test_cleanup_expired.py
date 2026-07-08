"""`cleanup_expired.py` tests (spec E6 required tests): the initial Qdrant scan
uses a created_at-range-only filter (no session filter — this job is
tenant-agnostic), orphan status is decided by a missing Redis doc record (not
by age alone, per the no-TTL persistent-account model), and `--dry-run` never
deletes. Qdrant and Redis are faked in-memory; no real service is touched.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.scripts import cleanup_expired


def _point(doc_id: str) -> SimpleNamespace:
    return SimpleNamespace(payload={"doc_id": doc_id})


class FakeQdrant:
    """One page of points on the first `scroll` call, then end-of-scroll.
    Records every scroll filter and delete selector it was called with."""

    def __init__(self, points: list[SimpleNamespace]) -> None:
        self.points = points
        self.scroll_calls: list = []
        self.delete_calls: list = []

    async def scroll(self, *, collection_name, scroll_filter, limit, offset, **kwargs):
        self.scroll_calls.append(scroll_filter)
        if offset is not None:
            return [], None
        return self.points, None

    async def delete(self, *, collection_name, points_selector):
        self.delete_calls.append(points_selector)


class FakeRedis:
    """A doc_id has a Redis record iff it's in `existing` — anything else is
    an orphan (no account ever persisted it)."""

    def __init__(self, existing_doc_ids: set[str]) -> None:
        self.existing = existing_doc_ids

    async def hgetall(self, key: str) -> dict[str, str]:
        doc_id = key.split(":")[-1]
        return {"filename": "x"} if doc_id in self.existing else {}


@pytest.fixture
def patch_clients(monkeypatch):
    def _patch(*, points: list[SimpleNamespace], existing_doc_ids: set[str]):
        qdrant = FakeQdrant(points)
        redis = FakeRedis(existing_doc_ids)
        monkeypatch.setattr(cleanup_expired, "get_qdrant", lambda: qdrant)
        monkeypatch.setattr(cleanup_expired, "get_redis", lambda: redis)
        return qdrant, redis

    return _patch


async def test_no_candidates_deletes_nothing(patch_clients):
    qdrant, _ = patch_clients(points=[], existing_doc_ids=set())

    deleted = await cleanup_expired.cleanup_expired()

    assert deleted == 0
    assert qdrant.delete_calls == []


async def test_deletes_only_the_orphaned_doc_id(patch_clients):
    points = [_point("orphan-1"), _point("owned-1")]
    qdrant, _ = patch_clients(points=points, existing_doc_ids={"owned-1"})

    deleted = await cleanup_expired.cleanup_expired()

    assert deleted == 1
    assert len(qdrant.delete_calls) == 1
    selector = qdrant.delete_calls[0]
    assert selector.must[0].key == "doc_id"
    assert selector.must[0].match.value == "orphan-1"


async def test_dry_run_reports_but_deletes_nothing(patch_clients):
    points = [_point("orphan-1")]
    qdrant, _ = patch_clients(points=points, existing_doc_ids=set())

    deleted = await cleanup_expired.cleanup_expired(dry_run=True)

    assert deleted == 1
    assert qdrant.delete_calls == []


async def test_no_orphans_among_owned_docs_deletes_nothing(patch_clients):
    points = [_point("owned-1"), _point("owned-2")]
    qdrant, _ = patch_clients(points=points, existing_doc_ids={"owned-1", "owned-2"})

    deleted = await cleanup_expired.cleanup_expired()

    assert deleted == 0
    assert qdrant.delete_calls == []


async def test_scroll_filter_is_created_at_range_only_no_session_filter(patch_clients):
    qdrant, _ = patch_clients(points=[], existing_doc_ids=set())

    await cleanup_expired.cleanup_expired(grace_seconds=1800)

    assert len(qdrant.scroll_calls) == 1
    scroll_filter = qdrant.scroll_calls[0]
    assert len(scroll_filter.must) == 1
    condition = scroll_filter.must[0]
    assert condition.key == "created_at"
    assert condition.range.lt is not None
    assert not any(getattr(c, "key", None) == "session_id" for c in scroll_filter.must)
