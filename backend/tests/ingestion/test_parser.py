"""Parser tests (spec E2 Required tests): scanned-PDF detection and a
malformed PDF producing a clean error, never a traceback."""

import pytest

from backend.ingestion.errors import IngestValidationError
from backend.ingestion.parser import MIN_EXTRACTABLE_CHARS, is_pdf, parse_pdf


def _make_pdf(pages_text: list[str]) -> bytes:
    """Build a real, in-memory PDF with one page per string (empty string =
    a blank page) — avoids depending on a fixture file for parser unit tests.

    Uses `insert_textbox` (word-wrapped into the page's margins), not
    `insert_text` — the latter silently drops any text past the first line,
    which would make long test strings extract as only a few words.
    """
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


def test_is_pdf_checks_magic_bytes():
    assert is_pdf(b"%PDF-1.4\n...") is True
    assert is_pdf(b"not a pdf at all") is False
    assert is_pdf(b"") is False


def test_parse_pdf_returns_page_numbered_text():
    data = _make_pdf(["Hello world. " * 20, "Second page content. " * 20])
    pages = parse_pdf(data, max_pages=10)
    assert [p for p, _ in pages] == [1, 2]
    assert "Hello world." in pages[0][1]
    assert "Second page content." in pages[1][1]


def test_malformed_pdf_raises_clean_error_not_a_traceback():
    garbage = b"%PDF-1.4\n%garbage\nthis is not a real pdf structure" + b"\x00" * 50
    with pytest.raises(IngestValidationError) as exc_info:
        parse_pdf(garbage, max_pages=10)
    assert exc_info.value.error == "malformed_pdf"
    assert exc_info.value.status_code == 400


def test_too_many_pages_is_rejected():
    data = _make_pdf(["Some real text content here. " * 10 for _ in range(5)])
    with pytest.raises(IngestValidationError) as exc_info:
        parse_pdf(data, max_pages=3)
    assert exc_info.value.error == "too_many_pages"
    assert exc_info.value.status_code == 422


def test_scanned_pdf_with_no_extractable_text_is_rejected():
    data = _make_pdf(["", ""])  # blank pages: no text layer at all
    with pytest.raises(IngestValidationError) as exc_info:
        parse_pdf(data, max_pages=10)
    assert exc_info.value.error == "scanned_pdf"
    assert exc_info.value.status_code == 422


def _words_of_length(n: int) -> str:
    """`n` characters of space-separated filler — word-wrapping only swaps an
    existing space for a newline, so the extracted char count matches `n`
    exactly (a bare unbroken run of one character does not: the wrapper
    inserts extra newlines mid-word, inflating the count)."""
    text = ("hi " * (n // 3 + 1))[:n]
    return text


def test_extractable_text_just_under_threshold_is_scanned():
    short_text = _words_of_length(MIN_EXTRACTABLE_CHARS - 1)
    data = _make_pdf([short_text])
    with pytest.raises(IngestValidationError) as exc_info:
        parse_pdf(data, max_pages=10)
    assert exc_info.value.error == "scanned_pdf"


def test_extractable_text_at_threshold_passes():
    long_text = "word " * 100  # comfortably over MIN_EXTRACTABLE_CHARS
    data = _make_pdf([long_text])
    pages = parse_pdf(data, max_pages=10)
    assert len(pages) == 1
