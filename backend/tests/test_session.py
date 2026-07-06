"""Tenant dependency: a valid bearer JWT resolves to its `sub`; a
missing/garbage/expired token is a clean 401 (never a 500)."""

from datetime import UTC, datetime, timedelta

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from backend.middleware.jwt_auth import get_current_user_id, issue_jwt


def _app_with_dep() -> FastAPI:
    app = FastAPI()

    @app.get("/probe")
    async def probe(tenant_id: str = Depends(get_current_user_id)):
        return {"tenant_id": tenant_id}

    return app


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_valid_token_resolves_to_sub():
    client = TestClient(_app_with_dep())
    token = issue_jwt(user_id="user-123", email="a@b.com")
    resp = client.get("/probe", headers=_bearer(token))
    assert resp.status_code == 200
    assert resp.json()["tenant_id"] == "user-123"


def test_missing_header_is_401():
    client = TestClient(_app_with_dep())
    assert client.get("/probe").status_code == 401


def test_malformed_token_is_401():
    client = TestClient(_app_with_dep())
    assert client.get("/probe", headers=_bearer("not-a-jwt")).status_code == 401


def test_expired_token_is_401():
    client = TestClient(_app_with_dep())
    past = datetime.now(UTC) - timedelta(days=30)
    expired = issue_jwt(user_id="u", email="a@b.com", now=past)
    assert client.get("/probe", headers=_bearer(expired)).status_code == 401


def test_wrong_signature_is_401(monkeypatch):
    client = TestClient(_app_with_dep())
    token = issue_jwt(user_id="u", email="a@b.com")
    # Re-sign the app's verifier with a different secret ⇒ signature no longer checks out.
    from backend.utils.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("JWT_SECRET", "a-completely-different-secret")
    get_settings.cache_clear()
    assert client.get("/probe", headers=_bearer(token)).status_code == 401
