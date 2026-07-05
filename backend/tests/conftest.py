"""Shared fixtures. External services are mocked here so tests never hit real
APIs.
"""

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
}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    """Populate required env vars and clear the settings cache per test."""
    for key, value in _TEST_ENV.items():
        monkeypatch.setenv(key, value)
    from backend.utils.config import get_settings

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
    """Counts how many times the LiteLLM boundary was hit. `call_count` stays 0
    on any path that must never touch a model (e.g. the guardrail rail)."""

    def __init__(self) -> None:
        self.call_count = 0


@pytest.fixture
def assert_no_llm_calls():
    """Patch every LiteLLM entry point with a counter and yield the guard.

    Exercise the code under test, then `assert guard.call_count == 0`. We patch
    BOTH the module-level functions (`litellm.completion`/`acompletion`) AND the
    Router methods (`Router.acompletion`/`completion`) — DocChat's pipeline
    calls through a `litellm.Router(...)`, so patching only the module
    functions would miss a regression that routes through the Router. The
    stubs return None instead of raising so a swallowing try/except can't hide
    the call from the count.
    """
    import litellm
    from litellm.router import Router

    guard = _LLMCallGuard()

    def _sync(*args, **kwargs):
        guard.call_count += 1
        return None

    async def _async(*args, **kwargs):
        guard.call_count += 1
        return None

    with (
        patch.object(litellm, "completion", _sync),
        patch.object(litellm, "acompletion", _async),
        patch.object(Router, "completion", _sync),
        patch.object(Router, "acompletion", _async),
    ):
        yield guard
