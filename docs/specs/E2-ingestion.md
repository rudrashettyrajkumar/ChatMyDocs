# SPEC E2 — Ingestion: upload → parse → chunk → embed → upsert

**Epic:** E2 · **Depends on:** E1 · **Architecture refs:** §3.1, §5.1, §5.2, §7

## Objective
`POST /documents` accepts a PDF and streams SSE progress while it parses, chunks, embeds,
and upserts to Qdrant. Plus list/delete endpoints and the enforcement of all upload limits.
After this epic, a PDF can be uploaded via curl and its chunks verified in Qdrant.

## Deliverables
```
backend/ingestion/parser.py         # PyMuPDF: bytes → [(page_no, text)], scanned-PDF detection
backend/ingestion/chunker.py        # token-aware chunks with page_start/page_end
backend/ingestion/ingest_service.py # orchestrates the 4 steps, yields progress events
backend/api/documents.py            # POST (SSE progress) / GET / DELETE
backend/middleware/rate_limit.py    # Redis counters: docs/session, uploads/IP
backend/scripts/create_collection.py # idempotent: docchat_chunks + payload indexes
backend/tests/ (parser, chunker, ingest_service, documents API)
sample/sample.pdf                    # a public-domain PDF, 10–30 pages
```

## Requirements
1. **Validation before any work**: PDF magic bytes, size ≤ MAX_DOC_MB, page count ≤
   MAX_PAGES, session doc count < MAX_DOCS_PER_SESSION, IP upload counter. Each failure →
   structured 4xx JSON `{error, detail}` the UI can render directly.
2. **Parse** (PyMuPDF, in-memory only — never write the PDF to disk): per-page text.
   If total extractable text < 200 chars → 422 "This PDF appears to be scanned/image-only".
3. **Chunk** per §5.2: CHUNK_TOKENS/CHUNK_OVERLAP (tiktoken cl100k_base), prefer paragraph
   boundaries, hard-split oversized paragraphs, carry page_start/page_end and chunk_index
   through splits and overlaps correctly (overlap can straddle pages).
4. **Embed** in batches of 100 via `utils/embeddings.py`; on a failed batch retry once,
   then abort ingestion with a clean SSE error event and **delete any points already
   upserted for this doc_id** (no half-ingested ghosts).
5. **Upsert**: point id = UUID5(doc_id, chunk_index); payload exactly per §5.1 including
   `created_at` epoch float. Collection + payload indexes (session_id, doc_id, created_at)
   created by the idempotent script, called on startup too.
6. **Progress SSE**: events `{"stage": "parsing"}`, `{"stage": "chunking", "chunks": N}`,
   `{"stage": "embedding", "pct": 40}`, terminal `{"stage": "ready", "doc_id": …,
   "filename": …, "pages": N, "chunks": N}` or `{"stage": "error", "detail": …}`.
7. **Metadata in Redis** (TTL 24h): `dc:doc:{doc_id}` hash + `dc:session:{sid}:docs` set.
   GET /documents reads these; DELETE removes Redis keys and Qdrant points by doc_id
   filter (and only for the requesting session — check ownership).
8. Filenames are sanitized for display (strip paths, cap 80 chars); doc_id is server-side
   UUID v4 — never trust client identifiers.

## Acceptance criteria
- `curl` upload of sample.pdf streams progress and lands N chunks in Qdrant with correct
  payloads (spot-check pages).
- A 15MB file, a .txt renamed to .pdf, a 4th document, and a scanned PDF are each rejected
  with distinct, friendly errors.
- DELETE removes every point for that doc_id and it disappears from GET /documents.

## Required tests
- chunker: golden test — fixed input text → exact chunk boundaries, page mapping across a
  page break, overlap correctness. This is the most bug-prone code in the project.
- parser: scanned-PDF detection; malformed PDF → clean error, not a traceback.
- ingest_service: mocked embed+qdrant — progress event sequence, mid-embed failure →
  rollback deletes prior points.
- API: all four rejection cases; ownership check on DELETE (session A cannot delete
  session B's doc).
