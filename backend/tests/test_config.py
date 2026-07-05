"""Config defaults + env override behavior (spec E1 Required tests)."""

import pytest

from backend.utils.config import REQUIRED_IN_PROD, Settings


def test_defaults_when_env_present():
    s = Settings()
    assert s.ENV == "dev"
    assert s.REWRITER_MODEL == "openrouter/google/gemini-3.1-flash-lite-preview"
    assert s.ANSWERER_MODEL == "openrouter/google/gemini-3-flash-preview"
    assert s.EMBED_MODEL == "openrouter/google/gemini-embedding-001"
    assert s.QDRANT_COLLECTION == "docchat_chunks"
    assert s.MAX_CONCURRENT_LLM_CALLS == 8
    assert s.MAX_DOC_MB == 10
    assert s.MAX_PAGES == 100
    assert s.MAX_DOCS_PER_SESSION == 3
    assert s.MAX_QUESTIONS_PER_DAY == 25
    assert s.MAX_UPLOADS_PER_IP_DAY == 10
    assert s.RELEVANCE_THRESHOLD == pytest.approx(0.30)
    assert s.CHUNK_TOKENS == 450
    assert s.CHUNK_OVERLAP == 80
    assert s.SESSION_TTL_HOURS == 24
    assert s.EMBED_BATCH_SIZE == 100


def test_env_override(monkeypatch):
    monkeypatch.setenv("MAX_DOCS_PER_SESSION", "7")
    monkeypatch.setenv("ANSWERER_MODEL", "openrouter/google/other-model")
    s = Settings()
    assert s.MAX_DOCS_PER_SESSION == 7
    assert s.ANSWERER_MODEL == "openrouter/google/other-model"


def test_dev_boots_with_missing_keys(monkeypatch):
    for key in REQUIRED_IN_PROD:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("ENV", "dev")
    # Must not raise — dev boots with whatever is wired up.
    Settings()


def test_prod_fails_fast_on_missing_keys(monkeypatch):
    for key in REQUIRED_IN_PROD:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("ENV", "prod")
    with pytest.raises(ValueError, match="Missing required config in prod"):
        Settings()


def test_prod_boots_when_all_required_keys_present(monkeypatch):
    monkeypatch.setenv("ENV", "prod")
    for key in REQUIRED_IN_PROD:
        monkeypatch.setenv(key, "x")
    Settings()  # must not raise
