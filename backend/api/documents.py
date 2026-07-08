"""`POST/GET/DELETE /documents` (spec E2 Req 1/6/7/8, ARCHITECTURE §3.1/§7).

**Validation-before-streaming split (a deliberate, spec-driven design choice):**
every check that can be settled BEFORE any real work — magic bytes, size,
rate limits, and the full parse (page count + scanned-PDF detection, spec
Req 1/2's "422"/"4xx") — runs synchronously and returns a plain JSON body with
a real HTTP status code. Only once all of that has passed does the endpoint
commit to `text/event-stream`; from that point on, the response status is
already 200, so the only way left to report a failure (e.g. a mid-embed
failure, spec Req 4) is the SSE stream's own terminal `{"stage": "error"}`
event (spec Req 6). This keeps the pre-flight rejections trivially testable
as ordinary JSON responses while still matching the architecture's "SSE
progress" contract for the pipeline steps that actually stream.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator
from pathlib import PureWindowsPath

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse, StreamingResponse

from backend.api.deps import get_tenant_id
from backend.ingestion.errors import IngestValidationError
from backend.ingestion.ingest_service import run_ingestion
from backend.ingestion.parser import is_pdf, parse_pdf
from backend.llm.runconfig import BYOKError, Selection, from_headers
from backend.middleware.rate_limit import check_and_increment_ip_upload, check_session_doc_limit
from backend.services import embed_signature
from backend.utils import embeddings
from backend.utils.config import get_settings
from backend.utils.qdrant_client import get_qdrant
from backend.utils.redis_client import dc_key, get_redis
from backend.utils.sse import format_event

router = APIRouter()
_log = logging.getLogger("docchat.api.documents")

_FILENAME_MAX_LEN = 80
_DEFAULT_FILENAME = "document.pdf"


def _client_ip(request: Request) -> str:
    """Best-effort caller IP: Railway/most PaaS front the app with a proxy
    that sets `X-Forwarded-For`; fall back to the raw socket peer."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _sanitize_filename(name: str) -> str:
    """Strip any path components (POSIX or Windows) and cap length (spec
    Req 8) — never trust a client-supplied filename beyond display text."""
    stripped = PureWindowsPath(name).name if name else ""
    return stripped[:_FILENAME_MAX_LEN] if stripped else _DEFAULT_FILENAME


def _validate_pdf_bytes(data: bytes) -> None:
    if not is_pdf(data):
        raise IngestValidationError(
            "invalid_file", "This doesn't look like a PDF file.", status_code=400
        )
    max_bytes = get_settings().MAX_DOC_MB * 1024 * 1024
    if len(data) > max_bytes:
        raise IngestValidationError(
            "file_too_large",
            f"PDF exceeds the {get_settings().MAX_DOC_MB}MB limit.",
            status_code=413,
        )


async def _persist_metadata(
    *, doc_id: str, session_id: str, filename: str, pages: int, chunks: int
) -> None:
    """Best-effort: the vectors are already safely in Qdrant by the time this
    runs, so a Redis hiccup here degrades `GET /documents`'s listing, not the
    document itself (errors degrade, never break).

    No TTL: documents belong to a persistent account now, not a 24h anonymous
    session, so they live until the user deletes them (or the account is gone).
    """
    doc_key = dc_key("doc", doc_id)
    session_docs_key = dc_key("session", session_id, "docs")
    try:
        await get_redis().pipeline(
            (
                "HSET",
                doc_key,
                "filename",
                filename,
                "pages",
                pages,
                "chunks",
                chunks,
                "session_id",
                session_id,
                "created_at",
                time.time(),
            ),
            ("SADD", session_docs_key, doc_id),
        )
    except Exception as exc:  # noqa: BLE001 — metadata write must never break ingestion
        _log.warning(
            "failed to persist document metadata", extra={"doc_id": doc_id, "error": str(exc)}
        )


async def _stream_ingestion(
    pages: list[tuple[int, str]],
    *,
    doc_id: str,
    filename: str,
    session_id: str,
    embed_selection: Selection,
) -> AsyncIterator[str]:
    ready: dict | None = None
    ingestion = run_ingestion(
        pages,
        doc_id=doc_id,
        filename=filename,
        session_id=session_id,
        embed_selection=embed_selection,
    )
    async for event in ingestion:
        yield format_event("progress", event)
        if event.get("stage") == "ready":
            ready = event
    if ready is not None:
        # Pin the tenant's embedding space on first successful ingest so every
        # later upload and every query vector lives in the same space.
        await embed_signature.pin(session_id, embed_selection)
        await _persist_metadata(
            doc_id=doc_id,
            session_id=session_id,
            filename=filename,
            pages=ready["pages"],
            chunks=ready["chunks"],
        )


@router.post("/documents", response_model=None)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    session_id: str = Depends(get_tenant_id),
) -> StreamingResponse | JSONResponse:
    data = await file.read()
    client_ip = _client_ip(request)

    # BYOK embed headers + embedding-space pin are part of the pre-flight
    # (validation-before-streaming): a mixed-space upload is a fixable 4xx,
    # never a half-ingested document.
    try:
        cfg = from_headers(request.headers)
        embed_selection = embed_signature.request_selection(cfg)
    except (BYOKError, embeddings.EmbeddingError) as exc:
        return JSONResponse(status_code=400, content={"error": "byok_invalid", "detail": str(exc)})

    pinned = await embed_signature.get_pin(session_id)
    if pinned is not None and pinned != embeddings.signature(embed_selection):
        return JSONResponse(
            status_code=409,
            content={
                "error": "embedding_mismatch",
                "detail": (
                    f"Your existing documents are embedded with “{pinned}”. Switch back "
                    f"to that embedding model, or delete all documents to change spaces."
                ),
                "pinned": pinned,
            },
        )

    try:
        _validate_pdf_bytes(data)
        await check_and_increment_ip_upload(client_ip)
        await check_session_doc_limit(session_id)
        pages = parse_pdf(data, max_pages=get_settings().MAX_PAGES)
    except IngestValidationError as exc:
        return JSONResponse(
            status_code=exc.status_code, content={"error": exc.error, "detail": exc.detail}
        )

    doc_id = str(uuid.uuid4())  # server-generated — never trust a client identifier (Req 8)
    filename = _sanitize_filename(file.filename or "")

    return StreamingResponse(
        _stream_ingestion(
            pages,
            doc_id=doc_id,
            filename=filename,
            session_id=session_id,
            embed_selection=embed_selection,
        ),
        media_type="text/event-stream",
    )


@router.get("/documents")
async def list_documents(session_id: str = Depends(get_tenant_id)) -> list[dict]:
    redis = get_redis()
    try:
        doc_ids = await redis.smembers(dc_key("session", session_id, "docs"))
    except Exception as exc:  # noqa: BLE001 — a Redis outage must not break the page
        _log.warning("failed to list documents; degrading to empty", extra={"error": str(exc)})
        return []

    results: list[dict] = []
    stale: list[str] = []
    for doc_id in doc_ids:
        doc = await redis.hgetall(dc_key("doc", doc_id))
        if not doc:  # TTL already expired the hash; the set entry is a ghost
            stale.append(doc_id)
            continue
        results.append(
            {
                "doc_id": doc_id,
                "filename": doc["filename"],
                "pages": int(doc["pages"]),
                "chunks": int(doc["chunks"]),
                "uploaded_at": float(doc["created_at"]),
            }
        )
    for doc_id in stale:
        await redis.srem(dc_key("session", session_id, "docs"), doc_id)
    return results


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, session_id: str = Depends(get_tenant_id)) -> dict:
    from qdrant_client import models

    redis = get_redis()
    try:
        doc = await redis.hgetall(dc_key("doc", doc_id))
    except Exception as exc:  # noqa: BLE001 — can't verify ownership: fail closed, not 500
        _log.warning("delete: ownership check failed", extra={"doc_id": doc_id, "error": str(exc)})
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail="Try again in a moment."
        ) from exc

    # 404 for both "never existed" and "belongs to another session" — a 403
    # would leak whether the doc_id exists in someone else's session.
    if not doc or doc.get("session_id") != session_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Document not found.")

    try:
        await get_qdrant().delete(
            collection_name=get_settings().QDRANT_COLLECTION,
            points_selector=models.Filter(
                must=[models.FieldCondition(key="doc_id", match=models.MatchValue(value=doc_id))]
            ),
        )
        await redis.delete(dc_key("doc", doc_id))
        await redis.srem(dc_key("session", session_id, "docs"), doc_id)
    except Exception as exc:  # noqa: BLE001 — a partial delete must not surface as a 500
        _log.warning("delete: cleanup failed", extra={"doc_id": doc_id, "error": str(exc)})
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail="Try again in a moment."
        ) from exc
    # Deleting the last document releases the embedding-space pin, freeing the
    # account to re-upload with a different embedding model.
    await embed_signature.release_if_empty(session_id)
    return {"deleted": True}
