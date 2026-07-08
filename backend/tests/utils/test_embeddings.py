"""BYOK embeddings: provider base routing, the hard 768-dim contract, and
the server-default (demo) selection parsing."""

from unittest.mock import patch

import pytest

from backend.llm.runconfig import Selection
from backend.utils import embeddings
from backend.utils.embeddings import EmbeddingError, embed, server_default_selection, signature


class _FakeResponse:
    def __init__(self, body: dict):
        self._body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self._body


def _client_capturing(calls: list, body: dict):
    class _FakeClient:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, json=None):
            calls.append({"url": url, "headers": headers, "json": json})
            return _FakeResponse(body)

    return _FakeClient


def _ok_body(n: int, dim: int = 768) -> dict:
    return {"data": [{"index": i, "embedding": [0.1] * dim} for i in range(n)]}


async def test_gemini_selection_routes_to_gemini_openai_compat_base():
    calls: list = []
    sel = Selection(provider="gemini", model="gemini-embedding-001", api_key="AIza-x")
    with patch.object(embeddings.httpx, "AsyncClient", _client_capturing(calls, _ok_body(1))):
        vectors = await embed(["hello"], sel)
    assert len(vectors) == 1 and len(vectors[0]) == 768
    assert calls[0]["url"].startswith("https://generativelanguage.googleapis.com")
    assert calls[0]["json"]["dimensions"] == 768
    assert calls[0]["headers"]["Authorization"] == "Bearer AIza-x"


async def test_wrong_dimensionality_fails_loudly():
    sel = Selection(provider="openai", model="text-embedding-3-small", api_key="sk-x")
    fake_client = _client_capturing([], _ok_body(1, dim=1536))
    with patch.object(embeddings.httpx, "AsyncClient", fake_client):
        with pytest.raises(EmbeddingError, match="768"):
            await embed(["hello"], sel)


async def test_error_body_with_200_fails_fast():
    sel = Selection(provider="openrouter", model="qwen/qwen3-embedding-0.6b", api_key="k")
    body = {"error": {"message": "insufficient credits"}}
    with patch.object(embeddings.httpx, "AsyncClient", _client_capturing([], body)):
        with pytest.raises(EmbeddingError, match="insufficient credits"):
            await embed(["hello"], sel)


async def test_no_selection_uses_server_default(monkeypatch):
    calls: list = []
    with patch.object(embeddings.httpx, "AsyncClient", _client_capturing(calls, _ok_body(1))):
        await embed(["hello"])
    assert calls[0]["url"].startswith("https://openrouter.ai")
    assert calls[0]["json"]["model"] == "nvidia/llama-nemotron-embed-vl-1b-v2:free"


def test_server_default_selection_parses_env_id():
    sel = server_default_selection()
    assert sel.provider == "openrouter"
    assert sel.model == "nvidia/llama-nemotron-embed-vl-1b-v2:free"
    assert signature(sel) == "openrouter/nvidia/llama-nemotron-embed-vl-1b-v2:free"


async def test_empty_texts_short_circuit():
    assert await embed([]) == []
