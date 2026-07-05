"""PyMuPDF parsing — in memory only, never touches disk (ARCHITECTURE §3.1,
spec E2 Req 2).

Two checks live here because they require actually opening the PDF structure
(a cheap `fitz.open`, not full text extraction): page count and scanned/
image-only detection. The magic-byte sniff (`is_pdf`) is a free pre-check the
API layer runs before even trying to open the file. Every failure raises the
shared `IngestValidationError` (spec Req 1's "structured 4xx JSON") — this
module never lets a corrupt file surface as a raw traceback.
"""

from __future__ import annotations

from backend.ingestion.errors import IngestValidationError

PDF_MAGIC = b"%PDF-"
# Below this many extractable characters, treat the PDF as scanned/image-only
# (spec Req 2) — no OCR in v1 (ARCHITECTURE §3.1).
MIN_EXTRACTABLE_CHARS = 200


def is_pdf(data: bytes) -> bool:
    """Magic-byte sniff — cheap, pre-parse (spec Req 1)."""
    return data[:5] == PDF_MAGIC


def parse_pdf(data: bytes, *, max_pages: int) -> list[tuple[int, str]]:
    """Open and fully extract `data` in memory; return `[(page_no, text), ...]`,
    1-indexed.

    Raises `IngestValidationError` for: a corrupt/unreadable PDF structure, too
    many pages, or too little extractable text (scanned/image-only).
    """
    import fitz  # heavy import kept off this module's import path until used

    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:  # fitz raises its own error types; normalize them
        raise IngestValidationError(
            "malformed_pdf",
            "This file could not be read as a PDF.",
            status_code=400,
        ) from exc

    try:
        if doc.page_count > max_pages:
            raise IngestValidationError(
                "too_many_pages",
                f"This PDF has {doc.page_count} pages; the limit is {max_pages}.",
                status_code=422,
            )
        pages = [(i + 1, doc[i].get_text()) for i in range(doc.page_count)]
    finally:
        doc.close()

    total_chars = sum(len(text.strip()) for _, text in pages)
    if total_chars < MIN_EXTRACTABLE_CHARS:
        raise IngestValidationError(
            "scanned_pdf",
            "This PDF appears to be scanned/image-only — no extractable text was found.",
            status_code=422,
        )
    return pages
