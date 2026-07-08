"""Shared fixtures. External services are mocked here so tests never hit real
APIs.
"""

import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# A full set of required env vars so `create_app()` never warns/fails during
# collection, independent of whatever the developer's real .env holds.
_TEST_ENV = {
    "ENV": "dev",
    "OPENROUTER_API_KEY": "test-openrouter-key",
    "GROQ_API_KEY": "test-groq-key",
    "QDRANT_URL": "http://qdrant.test",
    "QDRANT_API_KEY": "test-qdrant-key",
    "UPSTASH_URL": "http://upstash.test",
    "UPSTASH_TOKEN": "test-upstash-token",
    "JWT_SECRET": "test-jwt-secret-not-for-prod",
}


def bearer(sub: str | None = None) -> dict[str, str]:
    """Mint an `Authorization: Bearer` header for a given tenant/account id.

    Data-route tests only need a signed token whose `sub` matches the id their
    faked Redis/Qdrant state is keyed on — no real user record required, since
    the data-route auth dependency is decode-only (`get_current_user_id`).
    """
    from backend.middleware.jwt_auth import issue_jwt

    sub = sub or str(uuid.uuid4())
    return {"Authorization": f"Bearer {issue_jwt(user_id=sub, email='t@example.com')}"}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    """Populate required env vars and clear the settings cache per test.

    Also disables reading the developer's real `.env`: tests must be hermetic,
    driven solely by `_TEST_ENV`, so the "missing key" config tests can actually
    observe a key as missing instead of it leaking in from a populated `.env`.
    """
    from backend.utils.config import Settings, get_settings

    # Clear any ambient value for a Settings field we don't explicitly pin, so
    # defaults are honoured. Needed because importing `litellm` runs load_dotenv()
    # and — under the shared MyShiva deps — pulls MyShiva's .env into os.environ
    # (e.g. MAX_CONCURRENT_LLM_CALLS=12), which would otherwise leak into config
    # tests. A test that wants an override still sets it after this autouse runs.
    for field in Settings.model_fields:
        if field not in _TEST_ENV:
            monkeypatch.delenv(field, raising=False)
    for key, value in _TEST_ENV.items():
        monkeypatch.setenv(key, value)

    monkeypatch.setitem(Settings.model_config, "env_file", None)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def app():
    from backend.main import create_app

    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app)


class _LLMCallGuard:
    """Counts how many times the LLM boundary was hit. `call_count` stays 0
    on any path that must never touch a model (e.g. the guardrail rail)."""

    def __init__(self) -> None:
        self.call_count = 0


@pytest.fixture
def assert_no_llm_calls():
    """Patch every LLM entry point with a counter and yield the guard.

    Exercise the code under test, then `assert guard.call_count == 0`. We patch
    BOTH the gateway's public calls (`complete`/`stream` — what agents use) AND
    `factory.build_chat_model` — constructing a LangChain model is the one
    unavoidable step of ANY call path, so a regression that bypasses the
    gateway still trips the counter. The stubs return inert values instead of
    raising so a swallowing try/except can't hide the call from the count.
    """
    from backend.llm import factory, gateway

    guard = _LLMCallGuard()

    def _sync(*args, **kwargs):
        guard.call_count += 1
        return None

    async def _async(*args, **kwargs):
        guard.call_count += 1
        return ""

    async def _agen(*args, **kwargs):
        guard.call_count += 1
        yield ""

    with (
        patch.object(gateway, "complete", _async),
        patch.object(gateway, "stream", _agen),
        patch.object(factory, "build_chat_model", _sync),
    ):
        yield guard
