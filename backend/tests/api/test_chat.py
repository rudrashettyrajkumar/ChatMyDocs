"""`/chat/stream` API: 429 once the daily question limit is hit, and the SSE
response contract — content-type + no-cache headers (spec E4 required tests).
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, patch


def _parse_sse(text: str) -> list[dict]:
    lines = (line for line in text.splitlines() if line.startswith("data: "))
    return [json.loads(line[len("data: ") :]) for line in lines]


def _sid() -> str:
    return str(uuid.uuid4())


def test_question_limit_returns_429(client):
    redis = AsyncMock()
    redis.get = AsyncMock(return_value="25")  # already at MAX_QUESTIONS_PER_DAY (default 25)
    with patch("backend.middleware.rate_limit.get_redis", return_value=redis):
        resp = client.post(
            "/chat/stream", json={"question": "hi"}, headers={"X-Session-Id": _sid()}
        )
    assert resp.status_code == 429
    assert resp.json()["error"] == "rate_limited"


def test_chat_stream_is_sse_with_no_cache_headers_and_valid_frames(client):
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)  # under the question limit
    redis.smembers = AsyncMock(return_value=[])  # no documents -> no-docs canned path
    redis.lrange = AsyncMock(return_value=[])
    with (
        patch("backend.middleware.rate_limit.get_redis", return_value=redis),
        patch("backend.api.chat.get_redis", return_value=redis),
        patch("backend.services.history.get_redis", return_value=redis),
    ):
        resp = client.post(
            "/chat/stream", json={"question": "hi"}, headers={"X-Session-Id": _sid()}
        )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert resp.headers["cache-control"] == "no-cache"
    assert resp.headers["x-accel-buffering"] == "no"
    events = _parse_sse(resp.text)
    assert events[-1] == {}  # the terminal `done` event carries no fields
    assert events[-2] == {"sources": []}


def test_missing_session_id_is_400(client):
    resp = client.post("/chat/stream", json={"question": "hi"})
    assert resp.status_code == 400
