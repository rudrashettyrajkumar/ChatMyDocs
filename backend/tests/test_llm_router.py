"""LLM router: model list construction, semaphore cap, failover chain shape."""

import pytest

from backend.utils.config import Settings
from backend.utils.llm_router import ROLE_TIMEOUTS, _build_model_list, _check_role, _key_for


def test_build_model_list_has_primary_then_groq_fallback_per_role(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setenv("GROQ_API_KEY", "groq-key")
    s = Settings()
    model_list = _build_model_list(s)

    rewriter_deps = [d for d in model_list if d["model_name"] == "rewriter"]
    answerer_deps = [d for d in model_list if d["model_name"] == "answerer"]

    assert len(rewriter_deps) == 2
    assert rewriter_deps[0]["litellm_params"]["model"] == s.REWRITER_MODEL
    assert rewriter_deps[1]["litellm_params"]["model"] == "groq/llama-3.3-70b-versatile"

    assert len(answerer_deps) == 2
    assert answerer_deps[0]["litellm_params"]["model"] == s.ANSWERER_MODEL
    assert answerer_deps[1]["litellm_params"]["model"] == "groq/llama-3.3-70b-versatile"


def test_key_for_picks_provider_credential():
    s = Settings(OPENROUTER_API_KEY="or-key", GROQ_API_KEY="groq-key")
    assert _key_for("groq/llama-3.3-70b-versatile", s) == "groq-key"
    assert _key_for("openrouter/google/gemini-3-flash-preview", s) == "or-key"


def test_unknown_role_raises():
    with pytest.raises(ValueError, match="unknown LLM role"):
        _check_role("nonexistent")


def test_role_timeouts_defined_for_both_roles():
    assert set(ROLE_TIMEOUTS) == {"rewriter", "answerer"}
    assert ROLE_TIMEOUTS["rewriter"] > 0
    assert ROLE_TIMEOUTS["answerer"] > 0


async def test_complete_goes_through_router(assert_no_llm_calls):
    """Sanity: complete() actually hits the Router (guard counts > 0), proving
    no direct litellm bypass exists in this module."""
    import backend.utils.llm_router as llm_router

    llm_router._router = None
    llm_router._semaphore = None

    await llm_router.complete("rewriter", [{"role": "user", "content": "hi"}])
    assert assert_no_llm_calls.call_count == 1
