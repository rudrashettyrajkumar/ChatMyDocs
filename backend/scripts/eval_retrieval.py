"""Retrieval quality eval harness (spec E3 Req 6) — NOT a pytest suite.

Run deliberately, against LIVE Qdrant + LIVE OpenRouter embeddings, once
`.env` is filled in with real credentials:

    python -m backend.scripts.eval_retrieval

Ingests `sample/sample.pdf` under a fixed eval session/doc id (idempotent —
re-running upserts the same points rather than duplicating them, same
uuid5(doc_id, chunk_index) point-id scheme as `ingest_service.py`), then runs
the 15 hand-written questions in `eval_questions.json` through the real
`retrieval_agent.retrieve()`. Each question is a single query — this harness
bypasses `rewrite_agent` on purpose: it measures retrieval quality in
isolation, before the chat pipeline (E4) wires rewriting on top of it.

Scoring (hand-labeled by expected page in `eval_questions.json`):
- Answerable question (non-empty `expected_pages`) → HIT if any of the top-3
  fused chunks' page range intersects `expected_pages`.
- The one deliberately-unanswerable question (`expected_pages: []`) → HIT if
  `low_relevance=True`, i.e. the system correctly recognizes the documents
  don't cover it. This is the signal used to calibrate
  `RELEVANCE_THRESHOLD` — see the report's per-question scores.

Writes `eval_report.md` next to this script (top-3 chunks + scores per
question) and exits non-zero if fewer than 12/15 questions hit (spec Req 6 /
E3 acceptance criteria).
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from backend.agents.retrieval_agent import RetrievalResult, retrieve
from backend.ingestion.chunker import chunk_pages
from backend.ingestion.parser import parse_pdf
from backend.scripts.create_collection import ensure_collection
from backend.utils.config import get_settings
from backend.utils.embeddings import embed
from backend.utils.qdrant_client import get_qdrant

_ROOT = Path(__file__).resolve().parents[2]
_SAMPLE_PDF = _ROOT / "sample" / "sample.pdf"
_QUESTIONS_PATH = Path(__file__).resolve().parent / "eval_questions.json"
_REPORT_PATH = Path(__file__).resolve().parent / "eval_report.md"

# Fixed ids so re-running the harness upserts the SAME points (idempotent,
# spec Req 6) instead of accumulating duplicate copies of sample.pdf.
_EVAL_SESSION_ID = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
_EVAL_DOC_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
_EVAL_FILENAME = "sample.pdf"

_PASS_THRESHOLD = 12
_TOP_N_FOR_SCORING = 3


def _point_id(chunk_index: int) -> str:
    """Same uuid5(doc_id, chunk_index) scheme as ingest_service._point_id —
    re-running this harness overwrites rather than duplicates."""
    return str(uuid.uuid5(uuid.UUID(_EVAL_DOC_ID), str(chunk_index)))


async def _ingest_sample() -> int:
    """Idempotent ingest of sample.pdf under the fixed eval doc/session id.
    Returns the chunk count."""
    await ensure_collection()
    settings = get_settings()
    data = _SAMPLE_PDF.read_bytes()
    pages = parse_pdf(data, max_pages=settings.MAX_PAGES)
    chunks = chunk_pages(pages)
    texts = [c.text for c in chunks]
    vectors = await embed(texts)

    from qdrant_client import models

    created_at = time.time()
    points = [
        models.PointStruct(
            id=_point_id(chunk.chunk_index),
            vector=vector,
            payload={
                "session_id": _EVAL_SESSION_ID,
                "doc_id": _EVAL_DOC_ID,
                "filename": _EVAL_FILENAME,
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
                "chunk_index": chunk.chunk_index,
                "text": chunk.text,
                "created_at": created_at,
            },
        )
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]
    await get_qdrant().upsert(collection_name=settings.QDRANT_COLLECTION, points=points)
    return len(points)


def _page_overlaps(page_start: int, page_end: int, expected_pages: list[int]) -> bool:
    return any(page_start <= p <= page_end for p in expected_pages)


def _score(question: dict[str, Any], result: RetrievalResult) -> tuple[bool, str]:
    top3 = result.chunks[:_TOP_N_FOR_SCORING]
    expected = question["expected_pages"]
    if expected:
        hit = any(_page_overlaps(c.page_start, c.page_end, expected) for c in top3)
        reason = "matched expected page" if hit else "no top-3 chunk matched expected page"
    else:
        hit = result.low_relevance
        reason = (
            "correctly flagged low_relevance"
            if hit
            else "NOT flagged low_relevance (calibrate RELEVANCE_THRESHOLD)"
        )
    return hit, reason


async def _run_questions() -> tuple[int, int, list[dict[str, Any]]]:
    questions = json.loads(_QUESTIONS_PATH.read_text(encoding="utf-8"))
    records: list[dict[str, Any]] = []
    for q in questions:
        result = await retrieve([q["question"]], session_id=_EVAL_SESSION_ID)
        hit, reason = _score(q, result)
        records.append({"question": q, "result": result, "hit": hit, "reason": reason})
    hits = sum(1 for r in records if r["hit"])
    return hits, len(questions), records


def _write_report(hits: int, total: int, records: list[dict[str, Any]]) -> None:
    lines = [
        "# DocChat Retrieval Eval Report",
        "",
        f"RELEVANCE_THRESHOLD = {get_settings().RELEVANCE_THRESHOLD}",
        "",
        f"**Result: {hits}/{total} questions hit "
        f"(pass threshold: {_PASS_THRESHOLD}/{total})**",
        "",
    ]
    for record in records:
        q, result, hit, reason = (
            record["question"],
            record["result"],
            record["hit"],
            record["reason"],
        )
        top3 = result.chunks[:_TOP_N_FOR_SCORING]
        lines.append(f"## Q{q['id']} [{q['type']}] — {'HIT' if hit else 'MISS'}")
        lines.append(f"**Question:** {q['question']}")
        lines.append(
            f"**Expected pages:** {q['expected_pages'] or '(none — unanswerable)'}"
        )
        lines.append(
            f"**low_relevance:** {result.low_relevance}  ·  **Reason:** {reason}"
        )
        lines.append("")
        if top3:
            for c in top3:
                snippet = c.text[:160].replace("\n", " ")
                lines.append(
                    f'- [{c.n}] {c.citation_label} — score {c.score:.4f} — "{snippet}..."'
                )
        else:
            lines.append("- (no chunks returned)")
        lines.append("")
    _REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


async def main() -> int:
    print("Ingesting sample.pdf (idempotent)...")
    chunk_count = await _ingest_sample()
    print(f"Ingested {chunk_count} chunks from {_EVAL_FILENAME}.")

    print("Running eval questions against live Qdrant...")
    hits, total, records = await _run_questions()
    _write_report(hits, total, records)
    print(f"Result: {hits}/{total} — report written to {_REPORT_PATH}")

    return 0 if hits >= _PASS_THRESHOLD else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
