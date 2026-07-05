"""Orchestrates chunk → embed → upsert, yielding SSE-ready progress dicts
(ARCHITECTURE §3.1, spec E2 Req 3-6).

Parsing (and its validation) happens in `api/documents.py` BEFORE this
generator starts — every failure detectable up front (bad file, size, page
count, scanned PDF, quota) is a plain 4xx response, per spec Req 1's
"structured 4xx JSON". Once this generator is running, the HTTP response has
already committed to `text/event-stream`, so the only way left to report a
failure is a terminal `{"stage": "error", ...}` event (spec Req 6) — there is
no separate exception path back to the caller; the generator simply yields
that event and returns.

Embedding batches follow spec Req 4 exactly: one retry on failure, then abort
and delete any points already upserted for this `doc_id` — no half-ingested
ghosts survive a failed run.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from backend.ingestion.chunker import Chunk, chunk_pages
from backend.utils.config import get_settings
from backend.utils.embeddings import EmbeddingError, embed
from backend.utils.qdrant_client import get_qdrant

_log = logging.getLogger("docchat.ingest_service")


def _point_id(doc_id: str, chunk_index: int) -> str:
    """Deterministic point id (spec Req 5): UUID5 of the doc + chunk index, so
    re-running ingestion for the same doc_id/chunk_index overwrites cleanly."""
    return str(uuid.uuid5(uuid.UUID(doc_id), str(chunk_index)))


def _payload(
    chunk: Chunk, *, session_id: str, doc_id: str, filename: str, created_at: float
) -> dict[str, Any]:
    """Exactly the fields ARCHITECTURE §5.1 specifies — no more, no less."""
    return {
        "session_id": session_id,
        "doc_id": doc_id,
        "filename": filename,
        "page_start": chunk.page_start,
        "page_end": chunk.page_end,
        "chunk_index": chunk.chunk_index,
        "text": chunk.text,
        "created_at": created_at,
    }


async def _delete_doc_points(collection: str, doc_id: str) -> None:
    """Rollback: remove every point already upserted for `doc_id` (spec Req 4).
    Filter-based, so it's correct regardless of which batch failed.

    Best-effort: this already runs from an except-path (embed/upsert just
    failed), so a SECOND failure here (e.g. Qdrant itself is unreachable) must
    not propagate — the caller still needs to yield its `{"stage": "error"}`
    event. A failed rollback risks a few orphan points; a broken SSE stream
    with no terminal event is worse (spec Req 6, "errors degrade, never break").
    """
    from qdrant_client import models

    try:
        await get_qdrant().delete(
            collection_name=collection,
            points_selector=models.Filter(
                must=[models.FieldCondition(key="doc_id", match=models.MatchValue(value=doc_id))]
            ),
        )
    except Exception as exc:  # noqa: BLE001 — rollback is best-effort, never re-raises
        _log.warning(
            "rollback delete failed; some points may be orphaned",
            extra={"doc_id": doc_id, "error": str(exc)},
        )


async def run_ingestion(
    pages: list[tuple[int, str]],
    *,
    doc_id: str,
    filename: str,
    session_id: str,
) -> AsyncIterator[dict[str, Any]]:
    """Yield progress events per spec Req 6's exact shapes:

    `{"stage": "parsing"}` → `{"stage": "chunking", "chunks": N}` →
    `{"stage": "embedding", "pct": P}` (one per batch) → terminal
    `{"stage": "ready", "doc_id", "filename", "pages", "chunks"}` or
    `{"stage": "error", "detail"}`.
    """
    settings = get_settings()
    collection = settings.QDRANT_COLLECTION

    yield {"stage": "parsing"}

    chunks = chunk_pages(pages)
    yield {"stage": "chunking", "chunks": len(chunks)}

    total = len(chunks)
    created_at = time.time()
    batch_size = settings.EMBED_BATCH_SIZE
    done = 0

    for start in range(0, total, batch_size):
        batch = chunks[start : start + batch_size]
        texts = [c.text for c in batch]

        try:
            vectors = await embed(texts)
        except EmbeddingError:
            try:
                vectors = await embed(texts)  # one retry, per spec Req 4
            except EmbeddingError as exc:
                _log.warning("embedding failed twice; rolling back", extra={"doc_id": doc_id})
                await _delete_doc_points(collection, doc_id)
                yield {"stage": "error", "detail": f"Embedding failed: {exc}"}
                return

        from qdrant_client import models

        points = [
            models.PointStruct(
                id=_point_id(doc_id, chunk.chunk_index),
                vector=vector,
                payload=_payload(
                    chunk,
                    session_id=session_id,
                    doc_id=doc_id,
                    filename=filename,
                    created_at=created_at,
                ),
            )
            for chunk, vector in zip(batch, vectors, strict=True)
        ]

        try:
            await get_qdrant().upsert(collection_name=collection, points=points)
        except Exception as exc:  # noqa: BLE001 — any upsert failure must roll back cleanly
            _log.warning("upsert failed; rolling back", extra={"doc_id": doc_id})
            await _delete_doc_points(collection, doc_id)
            yield {"stage": "error", "detail": f"Storage failed: {exc}"}
            return

        done += len(batch)
        pct = int(100 * done / total) if total else 100
        yield {"stage": "embedding", "pct": pct}

    yield {
        "stage": "ready",
        "doc_id": doc_id,
        "filename": filename,
        "pages": max((page_no for page_no, _ in pages), default=0),
        "chunks": total,
    }
