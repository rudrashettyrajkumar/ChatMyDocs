"""Gateway chain semantics: demo failover, BYOK no-fallback, mid-stream
propagation, and text normalization of block-style content."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.llm import gateway
from backend.llm.gateway import LLMUnavailable, complete, stream
from backend.llm.runconfig import DEFAULT, RunConfig, Selection

_MSGS = [{"role": "user", "content": "hi"}]
_BYOK = RunConfig(chat=Selection(provider="groq", model="llama-3.3-70b-versatile", api_key="k"))


class _FakeModel:
    """Stands in for any LangChain chat model at the factory boundary."""

    def __init__(self, reply: str | None = None, tokens: list[str] | None = None,
                 fail: bool = False, fail_after: int | None = None):
        self.reply = reply
        self.tokens = tokens or []
        self.fail = fail
        self.fail_after = fail_after

    def bind(self, **_kw):
        return self

    async def ainvoke(self, _messages):
        if self.fail:
            raise RuntimeError("provider down")
        return SimpleNamespace(content=self.reply)

    async def astream(self, _messages):
        if self.fail:
            raise RuntimeError("provider down")
        for i, token in enumerate(self.tokens):
            if self.fail_after is not None and i >= self.fail_after:
                raise RuntimeError("died mid-stream")
            yield SimpleNamespace(content=token)


def _factory_returning(*models: _FakeModel):
    """A build_chat_model stub yielding `models` in construction order."""
    queue = list(models)

    def _build(selection, *, timeout, streaming=False):
        return queue.pop(0)

    return _build


async def test_demo_mode_fails_over_to_second_deployment():
    # conftest env sets both OPENROUTER and GROQ keys → a 2-deployment chain.
    with patch.object(
        gateway.factory,
        "build_chat_model",
        side_effect=_factory_returning(_FakeModel(fail=True), _FakeModel(reply="from fallback")),
    ):
        text = await complete("rewriter", _MSGS, DEFAULT)
    assert text == "from fallback"


async def test_demo_failure_detail_names_free_tier_and_byok_fix():
    # Both demo deployments fail → the user learns it's the free tier and
    # that bringing their own key is the fix (never a raw traceback).
    with patch.object(
        gateway.factory,
        "build_chat_model",
        side_effect=_factory_returning(_FakeModel(fail=True), _FakeModel(fail=True)),
    ):
        with pytest.raises(LLMUnavailable) as exc_info:
            await complete("rewriter", _MSGS, DEFAULT)
    detail = exc_info.value.user_detail
    assert "free-tier" in detail
    assert "own API key" in detail


async def test_byok_failure_raises_with_fixable_detail_and_no_fallback():
    build_calls = []

    def _build(selection, *, timeout, streaming=False):
        build_calls.append(selection)
        return _FakeModel(fail=True)

    with patch.object(gateway.factory, "build_chat_model", side_effect=_build):
        with pytest.raises(LLMUnavailable) as exc_info:
            await complete("answerer", _MSGS, _BYOK)
    # Exactly ONE deployment tried: a broken user key must never burn demo credit.
    assert build_calls == [_BYOK.chat]
    assert "llama-3.3-70b-versatile" in exc_info.value.user_detail
    assert "API key" in exc_info.value.user_detail


async def test_stream_yields_tokens_and_failover_before_first_token():
    with patch.object(
        gateway.factory,
        "build_chat_model",
        side_effect=_factory_returning(
            _FakeModel(fail=True), _FakeModel(tokens=["a", "b", "c"])
        ),
    ):
        out = [t async for t in stream("answerer", _MSGS, DEFAULT)]
    assert out == ["a", "b", "c"]


async def test_stream_mid_stream_failure_propagates_no_substitution():
    with patch.object(
        gateway.factory,
        "build_chat_model",
        side_effect=_factory_returning(
            _FakeModel(tokens=["a", "b"], fail_after=1), _FakeModel(tokens=["never"])
        ),
    ):
        received = []
        with pytest.raises(RuntimeError, match="died mid-stream"):
            async for token in stream("answerer", _MSGS, DEFAULT):
                received.append(token)
    assert received == ["a"]  # tokens already sent stay sent; no second model


async def test_unknown_role_fails_loudly():
    with pytest.raises(ValueError, match="unknown LLM role"):
        await complete("summarizer", _MSGS, DEFAULT)


def test_text_of_normalizes_anthropic_block_lists():
    blocks = [
        {"type": "text", "text": "Hello "},
        {"type": "tool_use"},
        {"type": "text", "text": "world"},
    ]
    assert gateway._text_of(blocks) == "Hello world"
    assert gateway._text_of("plain") == "plain"
    assert gateway._text_of(None) == ""
