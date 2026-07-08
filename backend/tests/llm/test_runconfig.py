"""RunConfig header parsing: demo default, valid BYOK trios, and every
user-correctable rejection (unknown provider, missing key, non-embed provider)."""

import pytest

from backend.llm.runconfig import DEFAULT, BYOKError, from_headers


def test_no_headers_is_demo_mode():
    cfg = from_headers({})
    assert cfg == DEFAULT
    assert cfg.chat is None and cfg.embed is None
    assert not cfg.is_byok


def test_valid_groq_chat_headers_parse():
    cfg = from_headers(
        {
            "x-llm-provider": "groq",
            "x-llm-model": "llama-3.3-70b-versatile",
            "x-llm-key": "gsk_test123",
        }
    )
    assert cfg.chat is not None
    assert cfg.chat.provider == "groq"
    assert cfg.chat.model == "llama-3.3-70b-versatile"
    assert cfg.chat.api_key == "gsk_test123"
    assert cfg.embed is None  # halves are independent


def test_provider_is_case_insensitive():
    cfg = from_headers({"x-llm-provider": "Anthropic", "x-llm-key": "sk-ant-x"})
    assert cfg.chat.provider == "anthropic"


def test_missing_model_falls_back_to_provider_recommended():
    cfg = from_headers({"x-llm-provider": "anthropic", "x-llm-key": "sk-ant-x"})
    assert cfg.chat.model == "claude-sonnet-5"  # the catalog's recommended pick


def test_unknown_catalog_model_passes_through():
    # Permissive by design: providers ship models faster than the catalog updates.
    cfg = from_headers(
        {"x-llm-provider": "groq", "x-llm-model": "brand-new-model", "x-llm-key": "gsk_x"}
    )
    assert cfg.chat.model == "brand-new-model"


def test_unknown_provider_rejected():
    with pytest.raises(BYOKError, match="unknown provider"):
        from_headers({"x-llm-provider": "notreal", "x-llm-key": "k"})


def test_key_required_when_provider_sent():
    with pytest.raises(BYOKError, match="X-LLM-Key"):
        from_headers({"x-llm-provider": "groq"})


def test_embed_rejects_non_embedding_provider():
    # Groq/Anthropic serve no embedding models — must fail loudly, not 500 later.
    with pytest.raises(BYOKError, match="cannot serve embeddings"):
        from_headers({"x-embed-provider": "groq", "x-embed-key": "gsk_x"})


def test_valid_embed_headers_parse_with_recommended_default_model():
    cfg = from_headers({"x-embed-provider": "openrouter", "x-embed-key": "sk-or-x"})
    assert cfg.embed.provider == "openrouter"
    assert cfg.embed.model == "qwen/qwen3-embedding-0.6b"


def test_key_with_whitespace_rejected():
    with pytest.raises(BYOKError, match="invalid X-LLM-Key"):
        from_headers({"x-llm-provider": "groq", "x-llm-key": "bad key"})
