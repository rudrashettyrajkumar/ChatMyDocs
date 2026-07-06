"""`/auth` routes: register → login → me happy path, plus the rejections
(duplicate email 409, wrong password 401, bad token 401) and validation.

The user store is faked in-memory (hashes, strings, HSET/SET pipeline) so the
real hashing + JWT code runs end to end without touching Upstash.
"""

from __future__ import annotations

import pytest


class FakeUserRedis:
    """Enough of Upstash for the user store: hashes, string keys, pipeline."""

    def __init__(self) -> None:
        self.hashes: dict[str, dict[str, str]] = {}
        self.strings: dict[str, str] = {}

    async def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    async def get(self, key):
        return self.strings.get(key)

    async def pipeline(self, *commands):
        results = []
        for name, key, *args in commands:
            if name == "HSET":
                self.hashes.setdefault(key, {}).update(
                    {k: str(v) for k, v in zip(args[0::2], args[1::2], strict=True)}
                )
                results.append(len(args) // 2)
            elif name == "SET":
                self.strings[key] = str(args[0])
                results.append("OK")
            else:
                raise AssertionError(f"unexpected pipeline command: {name}")
        return results


@pytest.fixture
def fake_users(monkeypatch):
    redis = FakeUserRedis()
    monkeypatch.setattr("backend.services.users.get_redis", lambda: redis)
    return redis


def test_register_then_me(client, fake_users):
    resp = client.post(
        "/auth/register",
        json={"email": "Alice@Example.com", "password": "hunter2hunter", "name": "Alice"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["user"]["email"] == "alice@example.com"  # normalized
    assert body["user"]["name"] == "Alice"
    token = body["access_token"]

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "alice@example.com"


def test_register_duplicate_email_is_409(client, fake_users):
    payload = {"email": "dup@example.com", "password": "longenough1"}
    assert client.post("/auth/register", json=payload).status_code == 201
    resp = client.post("/auth/register", json=payload)
    assert resp.status_code == 409


def test_login_success_and_wrong_password(client, fake_users):
    client.post("/auth/register", json={"email": "bob@example.com", "password": "correct-pass-1"})

    ok = client.post("/auth/login", json={"email": "bob@example.com", "password": "correct-pass-1"})
    assert ok.status_code == 200
    assert ok.json()["user"]["email"] == "bob@example.com"

    bad = client.post("/auth/login", json={"email": "bob@example.com", "password": "wrong-pass-1"})
    assert bad.status_code == 401


def test_login_unknown_email_is_401(client, fake_users):
    resp = client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": "whatever12"}
    )
    assert resp.status_code == 401


def test_me_requires_valid_token(client, fake_users):
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_register_rejects_bad_email_and_short_password(client, fake_users):
    assert client.post(
        "/auth/register", json={"email": "not-an-email", "password": "longenough1"}
    ).status_code == 422
    assert client.post(
        "/auth/register", json={"email": "ok@example.com", "password": "short"}
    ).status_code == 422
