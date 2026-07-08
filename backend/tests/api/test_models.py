"""`/api/models` surface: auth-gated catalog with runtime facts, and the
validate endpoint's ok/false contract (a bad key is a result, not a 500)."""

from unittest.mock import AsyncMock, patch

from backend.tests.conftest import bearer


def test_catalog_requires_auth(client):
    assert client.get("/api/models").status_code == 401


def test_catalog_lists_all_five_providers_with_key_steps(client):
    with patch(
        "backend.api.models.embed_signature.get_pin", new=AsyncMock(return_value=None)
    ):
        resp = client.get("/api/models", headers=bearer())
    assert resp.status_code == 200
    body = resp.json()
    ids = [p["id"] for p in body["providers"]]
    assert ids == ["groq", "openrouter", "openai", "anthropic", "gemini"]
    groq = body["providers"][0]
    assert groq["kind"] == "free"
    assert any("console.groq.com" in step for step in groq["key_steps"])
    assert any(m["free"] for m in groq["models"])
    assert body["demo_available"] is True  # conftest sets server keys
    assert body["embedding_pin"] is None
    assert body["embed_providers"] == ["openrouter", "openai", "gemini"]


def test_catalog_reports_embedding_pin(client):
    with patch(
        "backend.api.models.embed_signature.get_pin",
        new=AsyncMock(return_value="openrouter/qwen/qwen3-embedding-0.6b"),
    ):
        resp = client.get("/api/models", headers=bearer())
    assert resp.json()["embedding_pin"] == "openrouter/qwen/qwen3-embedding-0.6b"


def test_validate_rejects_bad_provider_as_ok_false(client):
    resp = client.post(
        "/api/models/validate",
        headers=bearer(),
        json={"provider": "notreal", "model": "x", "api_key": "k"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert "unknown provider" in body["detail"]


def test_validate_chat_key_happy_path(client):
    class _FakeModel:
        async def ainvoke(self, _msgs):
            from types import SimpleNamespace

            return SimpleNamespace(content="ok")

    with patch("backend.api.models.factory.build_chat_model", return_value=_FakeModel()):
        resp = client.post(
            "/api/models/validate",
            headers=bearer(),
            json={"provider": "groq", "model": "llama-3.3-70b-versatile", "api_key": "gsk_x"},
        )
    body = resp.json()
    assert body["ok"] is True
    assert "latency_ms" in body


def test_validate_provider_failure_reports_reason(client):
    with patch(
        "backend.api.models.factory.build_chat_model",
        side_effect=RuntimeError("401 invalid api key"),
    ):
        resp = client.post(
            "/api/models/validate",
            headers=bearer(),
            json={"provider": "openai", "model": "gpt-5.4-mini", "api_key": "sk-bad"},
        )
    body = resp.json()
    assert body["ok"] is False
    assert "invalid api key" in body["detail"]


def test_validate_embedding_key_uses_embed_path(client):
    with patch(
        "backend.api.models.embeddings.embed", new=AsyncMock(return_value=[[0.0] * 768])
    ) as embed_mock:
        resp = client.post(
            "/api/models/validate",
            headers=bearer(),
            json={
                "provider": "openrouter",
                "model": "qwen/qwen3-embedding-0.6b",
                "api_key": "sk-or-x",
                "kind": "embedding",
            },
        )
    assert resp.json()["ok"] is True
    embed_mock.assert_awaited_once()
    selection = embed_mock.await_args.args[1]
    assert selection.provider == "openrouter"
