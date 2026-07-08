"""`build_chat_model` provider wiring — real LangChain construction (no network).

Regression coverage for a live-testing finding: OpenRouter's free "reasoning"
models (Nemotron, gpt-oss, Qwen3) burn an unbounded hidden thinking budget
before the first visible token — measured 70+s of silence on Nemotron 3
Super — so every OpenRouter call binds `reasoning.enabled=false`. That field
is OpenRouter-only: Groq 400s on it (confirmed live), so it must never leak
to Groq/OpenAI/Anthropic/Gemini calls.
"""

from __future__ import annotations

from backend.llm.factory import build_chat_model
from backend.llm.runconfig import Selection


def test_openrouter_binds_reasoning_disabled():
    sel = Selection(provider="openrouter", model="nvidia/nemotron-3-nano-30b-a3b:free", api_key="k")
    model = build_chat_model(sel, timeout=5.0)
    assert getattr(model, "kwargs", None) == {"reasoning": {"enabled": False}}


def test_groq_does_not_bind_reasoning():
    sel = Selection(provider="groq", model="llama-3.3-70b-versatile", api_key="k")
    model = build_chat_model(sel, timeout=5.0)
    assert not hasattr(model, "kwargs")


def test_openai_does_not_bind_reasoning():
    sel = Selection(provider="openai", model="gpt-4o-mini", api_key="k")
    model = build_chat_model(sel, timeout=5.0)
    assert not hasattr(model, "kwargs")
