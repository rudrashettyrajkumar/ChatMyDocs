---
name: qdrant-rag
description: Qdrant + RAG patterns for this project — multi-tenant payload filtering, chunking with page tracking, batched embeddings, RRF fusion, relevance thresholds. Use when working on ingestion, retrieval, or anything touching Qdrant.
---

# Qdrant RAG patterns (DocChat)

## Multi-tenancy: one collection, mandatory filter
- Single collection `docchat_chunks` (768-dim, cosine). NEVER create per-session or
  per-doc collections — free tier limits and an anti-pattern besides.
- Payload indexes required: `session_id` (keyword), `doc_id` (keyword),
  `created_at` (float). Created idempotently by `scripts/create_collection.py`.
- The `session_id` filter is applied at ONE choke point inside `retrieval_agent.py`:

```python
qdrant.search(
    collection_name=settings.COLLECTION,
    query_vector=vec,
    query_filter=models.Filter(must=[models.FieldCondition(
        key="session_id", match=models.MatchValue(value=session_id))]),
    limit=8,
)
```

Call sites never build their own filter. A test asserts the filter is present on every
search call — do not weaken it.

## Chunking (the bug-prone part)
- 450 tokens, 80 overlap (tiktoken `cl100k_base`), prefer paragraph boundaries, hard-split
  only oversized paragraphs.
- Track `page_start`/`page_end` through both splitting AND overlap — a chunk whose overlap
  region crosses a page boundary spans pages. Write the golden test before the chunker.
- Point id = `uuid5(doc_id_namespace, str(chunk_index))` so re-ingestion upserts instead
  of duplicating.

## Embeddings
- `gemini-embedding-001` via OpenRouter, `dimensions=768`, batches of ≤100 texts per
  request. One batched call per pipeline step — never one call per text.
- Query embedding and document embedding use the SAME model/dims (obvious, but the #1
  silent-failure in RAG systems).

## Fusion & relevance
- Multi-query (2–4) top-8 each → Reciprocal Rank Fusion `k=60` → dedup by point id →
  top 6. Reference implementation: MyShiva `backend/utils/rrf.py` — port verbatim.
- `low_relevance = best_raw_cosine < settings.RELEVANCE_THRESHOLD` (calibrated by the
  eval harness, default 0.30). The flag flows to the answer prompt; retrieval never
  hides low-quality results itself.

## Hygiene
- Every point payload carries `created_at` (epoch float) for the 24h cleanup cron
  (`created_at` range filter delete).
- Failed mid-ingestion → delete already-upserted points for that doc_id (no ghosts).
- Deletes are always by filter (doc_id / created_at range), never by enumerating ids.
