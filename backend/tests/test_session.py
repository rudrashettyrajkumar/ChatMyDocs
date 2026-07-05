"""Session dependency: valid UUID passes, missing/garbage → 400
(spec E1 Required tests)."""

import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.deps import get_session_id


def _app_with_dep() -> FastAPI:
    from fastapi import Depends

    app = FastAPI()

    @app.get("/probe")
    async def probe(session_id: str = Depends(get_session_id)):
        return {"session_id": session_id}

    return app


def test_valid_uuid_v4_passes():
    client = TestClient(_app_with_dep())
    sid = str(uuid.uuid4())
    resp = client.get("/probe", headers={"X-Session-Id": sid})
    assert resp.status_code == 200
    assert resp.json()["session_id"] == sid


def test_missing_header_is_400():
    client = TestClient(_app_with_dep())
    resp = client.get("/probe")
    assert resp.status_code == 400


def test_malformed_uuid_is_400():
    client = TestClient(_app_with_dep())
    resp = client.get("/probe", headers={"X-Session-Id": "not-a-uuid"})
    assert resp.status_code == 400


def test_non_v4_uuid_is_400():
    client = TestClient(_app_with_dep())
    # UUID v1 (time-based), not v4.
    v1 = str(uuid.uuid1())
    resp = client.get("/probe", headers={"X-Session-Id": v1})
    assert resp.status_code == 400


def test_empty_header_is_400():
    client = TestClient(_app_with_dep())
    resp = client.get("/probe", headers={"X-Session-Id": ""})
    assert resp.status_code == 400
