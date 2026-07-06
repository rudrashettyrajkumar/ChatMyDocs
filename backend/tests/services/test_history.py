"""History service: load ordering, append shape, TTL, and Redis-outage
degradation (spec E4 required tests)."""

import json
from unittest.mock import AsyncMock, patch

from backend.services import history


def _redis_with(lrange=None):
    redis = AsyncMock()
    redis.lrange = AsyncMock(return_value=lrange or [])
    redis.pipeline = AsyncMock(return_value=[1, "OK", 1])
    return redis


async def test_load_turns_reverses_newest_first_storage_to_oldest_first():
    # LPUSH stores newest at index 0; load_turns must return oldest-first.
    stored = [
        json.dumps({"role": "assistant", "content": "second reply", "ts": 2.0}),
        json.dumps({"role": "user", "content": "second question", "ts": 1.5}),
        json.dumps({"role": "assistant", "content": "first reply", "ts": 1.0}),
        json.dumps({"role": "user", "content": "first question", "ts": 0.5}),
    ]
    redis = _redis_with(lrange=stored)
    with patch("backend.services.history.get_redis", return_value=redis):
        turns = await history.load_turns("sess-1")
    assert [t["content"] for t in turns] == [
        "first question",
        "first reply",
        "second question",
        "second reply",
    ]


async def test_load_turns_skips_corrupt_entries():
    redis = _redis_with(lrange=["not json", json.dumps({"role": "user", "content": "ok"})])
    with patch("backend.services.history.get_redis", return_value=redis):
        turns = await history.load_turns("sess-1")
    assert turns == [{"role": "user", "content": "ok"}]


async def test_load_turns_degrades_to_empty_on_redis_outage():
    redis = AsyncMock()
    redis.lrange = AsyncMock(side_effect=ConnectionError("redis unreachable"))
    with patch("backend.services.history.get_redis", return_value=redis):
        turns = await history.load_turns("sess-1")
    assert turns == []


async def test_append_turn_pushes_and_trims_without_ttl():
    redis = _redis_with()
    with patch("backend.services.history.get_redis", return_value=redis):
        await history.append_turn("sess-1", "user", "hello")
    redis.pipeline.assert_awaited_once()
    # No EXPIRE: history persists with the account, bounded only by the window.
    (lpush_cmd, ltrim_cmd) = redis.pipeline.await_args.args
    assert lpush_cmd[0] == "LPUSH"
    assert lpush_cmd[1] == "dc:history:sess-1"
    payload = json.loads(lpush_cmd[2])
    assert payload["role"] == "user"
    assert payload["content"] == "hello"
    assert "ts" in payload
    assert ltrim_cmd == ("LTRIM", "dc:history:sess-1", 0, 11)


async def test_append_turn_degrades_silently_on_redis_outage():
    redis = AsyncMock()
    redis.pipeline = AsyncMock(side_effect=ConnectionError("redis unreachable"))
    with patch("backend.services.history.get_redis", return_value=redis):
        await history.append_turn("sess-1", "user", "hello")  # must not raise
