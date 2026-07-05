"""The one 4xx error shape for every pre-stream ingestion check (spec E2 Req 1).

`POST /documents` rejects a bad upload — wrong magic bytes, oversized file,
too many pages, a scanned/image-only PDF, a session/IP over its quota — before
opening the SSE stream. Every one of those checks (parser.py, rate_limit.py)
raises this ONE exception type so `api/documents.py` can catch it in a single
place and return the exact `{error, detail}` JSON body the UI renders
directly, instead of FastAPI's default `{"detail": ...}` HTTPException wrapper.
"""

from __future__ import annotations


class IngestValidationError(Exception):
    """A pre-stream upload check failed. `error` is a stable machine code for
    the UI to branch on; `detail` is the human-readable message it can show
    verbatim."""

    def __init__(self, error: str, detail: str, *, status_code: int) -> None:
        self.error = error
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)
