"""Daily orphan cleanup (spec E6 Req 3, ARCHITECTURE §9).

**Why "orphan", not "24h TTL":** the original spec (pre-auth) wiped every
Qdrant point older than 24h — that matched the old anonymous-session design.
The v1.1 auth addendum (`docs/ARCHITECTURE.md` line 4) supersedes that:
documents now persist with the account, no TTL, until the user calls
`DELETE /documents/{doc_id}`. A blanket age sweep would therefore delete every
real user's real documents a day after upload — this script does NOT do that.

What it actually cleans: Qdrant chunks whose ingestion never got a matching
`dc:doc:{doc_id}` Redis record — the process crashing between the last
`upsert` and `documents.py::_persist_metadata`'s `HSET`, or that `HSET` itself
failing (a real, if rare, possibility: `_persist_metadata` deliberately
swallows Redis errors so a metadata hiccup can't fail the upload, per "errors
degrade, never break"). Those chunks are permanent, invisible, undeletable
garbage under the no-TTL model — nobody can list or delete them, since the
owning doc row never existed. Age is only a grace window (default 1h, comfortably
above any real ingestion) so we never race a run that's still in flight.

Run standalone:
    python -m backend.scripts.cleanup_expired [--dry-run] [--grace-seconds N]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import time

from backend.utils.config import get_settings
from backend.utils.qdrant_client import get_qdrant
from backend.utils.redis_client import dc_key, get_redis

_log = logging.getLogger("docchat.cleanup_expired")

# Ingestion (parse + embed + upsert) finishes in low tens of seconds even for
# MAX_PAGES; 1h leaves a wide margin so a slow-but-live run is never mistaken
# for an orphan.
DEFAULT_GRACE_SECONDS = 3600

_SCROLL_PAGE_SIZE = 256


async def _find_candidate_doc_ids(cutoff: float) -> set[str]:
    """Scan Qdrant for chunk doc_ids older than `cutoff` (created_at range
    filter only — no session filter, deliberately: this job is tenant-agnostic,
    it looks for ingestions with no owning account record at all)."""
    from qdrant_client import models

    client = get_qdrant()
    settings = get_settings()

    doc_ids: set[str] = set()
    offset = None
    while True:
        points, offset = await client.scroll(
            collection_name=settings.QDRANT_COLLECTION,
            scroll_filter=models.Filter(
                must=[models.FieldCondition(key="created_at", range=models.Range(lt=cutoff))]
            ),
            with_payload=["doc_id"],
            with_vectors=False,
            limit=_SCROLL_PAGE_SIZE,
            offset=offset,
        )
        for point in points:
            doc_id = point.payload.get("doc_id") if point.payload else None
            if doc_id:
                doc_ids.add(doc_id)
        if offset is None:
            break
    return doc_ids


async def _orphaned_doc_ids(candidates: set[str]) -> set[str]:
    """A candidate is orphaned iff it has no `dc:doc:{doc_id}` Redis hash —
    i.e. no account ever ended up owning it."""
    redis = get_redis()
    orphans: set[str] = set()
    for doc_id in candidates:
        doc = await redis.hgetall(dc_key("doc", doc_id))
        if not doc:
            orphans.add(doc_id)
    return orphans


async def _delete_doc_ids(doc_ids: set[str]) -> None:
    from qdrant_client import models

    client = get_qdrant()
    settings = get_settings()
    for doc_id in doc_ids:
        await client.delete(
            collection_name=settings.QDRANT_COLLECTION,
            points_selector=models.Filter(
                must=[models.FieldCondition(key="doc_id", match=models.MatchValue(value=doc_id))]
            ),
        )


async def cleanup_expired(
    *, grace_seconds: int = DEFAULT_GRACE_SECONDS, dry_run: bool = False
) -> int:
    """Delete orphaned (never-persisted) ingestions older than `grace_seconds`.

    Returns the number of orphaned doc_ids found (deleted, unless `dry_run`).
    """
    cutoff = time.time() - grace_seconds
    candidates = await _find_candidate_doc_ids(cutoff)
    orphans = await _orphaned_doc_ids(candidates)

    if not orphans:
        _log.info("cleanup: no orphaned documents found", extra={"candidates": len(candidates)})
        return 0

    if dry_run:
        _log.info(
            "cleanup: dry-run, would delete %d orphaned doc(s)",
            len(orphans),
            extra={"doc_ids": sorted(orphans)},
        )
        return len(orphans)

    await _delete_doc_ids(orphans)
    _log.info(
        "cleanup: deleted %d orphaned doc(s)", len(orphans), extra={"doc_ids": sorted(orphans)}
    )
    return len(orphans)


async def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="log what would be deleted, delete nothing"
    )
    parser.add_argument(
        "--grace-seconds",
        type=int,
        default=DEFAULT_GRACE_SECONDS,
        help=f"min age before an ingestion is considered (default {DEFAULT_GRACE_SECONDS})",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    deleted = await cleanup_expired(grace_seconds=args.grace_seconds, dry_run=args.dry_run)
    verb = "would delete" if args.dry_run else "deleted"
    print(f"{verb} {deleted} orphaned document(s)")


if __name__ == "__main__":
    asyncio.run(_main())
