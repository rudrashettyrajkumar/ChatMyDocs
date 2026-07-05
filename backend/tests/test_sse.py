"""SSE formatting + heartbeat helpers."""

import asyncio
import json

from backend.utils.sse import PING, format_event, format_token, with_heartbeat


def test_format_event_shape():
    frame = format_event("token", {"seq": 1, "t": "hi"}, event_id=1)
    assert frame == 'id: 1\nevent: token\ndata: {"seq": 1, "t": "hi"}\n\n'


def test_format_event_without_id_omits_id_line():
    frame = format_event("done", {"ok": True})
    assert not frame.startswith("id:")
    assert "event: done\n" in frame
    assert json.loads(frame.split("data: ", 1)[1].strip()) == {"ok": True}


def test_format_token_uses_seq_as_event_id():
    frame = format_token(3, "abc")
    assert frame.startswith("id: 3\n")
    assert '"seq": 3' in frame
    assert '"t": "abc"' in frame


async def _tokens(*parts, delay=0.0):
    for part in parts:
        if delay:
            await asyncio.sleep(delay)
        yield part


async def test_with_heartbeat_passes_tokens_through():
    out = [tok async for tok in with_heartbeat(_tokens("a", "b", "c"), interval=10)]
    assert out == ["a", "b", "c"]


async def test_with_heartbeat_emits_ping_on_silence():
    async def slow_tokens():
        await asyncio.sleep(0.05)
        yield "late"

    out = [tok async for tok in with_heartbeat(slow_tokens(), interval=0.01)]
    assert out[0] == PING
    assert out[-1] == "late"
