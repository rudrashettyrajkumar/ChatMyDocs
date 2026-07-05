"""Health: each dependency mocked up/down → correct aggregate status
(spec E1 Required tests)."""

from unittest.mock import AsyncMock, patch


def _get(client, *, qdrant_ok, redis_ok, llm_ok):
    with (
        patch(
            "backend.api.health._check_qdrant",
            new=AsyncMock(side_effect=None if qdrant_ok else RuntimeError("down")),
        ),
        patch(
            "backend.api.health._check_redis",
            new=AsyncMock(side_effect=None if redis_ok else RuntimeError("down")),
        ),
        patch(
            "backend.api.health._check_llm",
            new=AsyncMock(side_effect=None if llm_ok else RuntimeError("down")),
        ),
    ):
        return client.get("/health")


def test_all_up_returns_ok(client):
    resp = _get(client, qdrant_ok=True, redis_ok=True, llm_ok=True)
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "qdrant": "ok", "redis": "ok", "llm": "ok"}


def test_one_down_is_degraded_but_200(client):
    resp = _get(client, qdrant_ok=True, redis_ok=False, llm_ok=True)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["redis"] == "down"
    assert body["qdrant"] == "ok"
    assert body["llm"] == "ok"


def test_all_down_is_503(client):
    resp = _get(client, qdrant_ok=False, redis_ok=False, llm_ok=False)
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["qdrant"] == "down"
    assert body["redis"] == "down"
    assert body["llm"] == "down"


async def test_probe_never_raises():
    from backend.api.health import _probe

    async def _boom():
        raise TimeoutError("simulated")

    assert await _probe("x", _boom) == "down"
