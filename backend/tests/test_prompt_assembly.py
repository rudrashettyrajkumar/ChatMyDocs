"""Prompt assembly — golden test for the exact assembled prompt (spec E4
required tests)."""

from backend.agents.retrieval_agent import RetrievedChunk
from backend.utils import prompt_assembly

_CHUNKS = [
    RetrievedChunk(
        n=1,
        id="pt-1",
        doc_id="doc-1",
        filename="report.pdf",
        page_start=3,
        page_end=3,
        text="Revenue grew 12% year over year.",
        score=0.81,
        citation_label="report.pdf, p.3",
    ),
    RetrievedChunk(
        n=2,
        id="pt-2",
        doc_id="doc-1",
        filename="report.pdf",
        page_start=5,
        page_end=6,
        text="Risk factors include supply chain volatility.",
        score=0.77,
        citation_label="report.pdf, p.5–6",
    ),
]

_HISTORY = [
    {"role": "user", "content": "What is this document about?"},
    {"role": "assistant", "content": "It's an annual report [1]."},
]

_QUESTION = "What was the revenue growth?"


def test_system_prompt_is_identity_then_citation_rules():
    identity = (
        prompt_assembly._PROMPTS_DIR / "answerer_identity.md"
    ).read_text(encoding="utf-8").strip()
    citation = (
        prompt_assembly._PROMPTS_DIR / "citation_rules.md"
    ).read_text(encoding="utf-8").strip()
    assert prompt_assembly.system_prompt() == f"{identity}\n\n{citation}"


def test_user_turn_golden_assembly():
    turn = prompt_assembly.user_turn(_CHUNKS, _HISTORY, _QUESTION, low_relevance=False)
    expected = (
        "[CONTEXT]\n"
        "[1] report.pdf, p.3\n"
        "Revenue grew 12% year over year.\n\n"
        "[2] report.pdf, p.5–6\n"
        "Risk factors include supply chain volatility.\n\n"
        "[HISTORY]\n"
        "user: What is this document about?\n"
        "assistant: It's an annual report [1].\n\n"
        "[QUESTION]\n"
        "What was the revenue growth?"
    )
    assert turn == expected


def test_user_turn_low_relevance_note_is_prefixed():
    turn = prompt_assembly.user_turn(_CHUNKS, [], _QUESTION, low_relevance=True)
    assert turn.startswith(
        "[CONTEXT]\n(marked low relevance — this material may not answer the question)\n\n[1]"
    )


def test_user_turn_no_chunks_and_no_history():
    turn = prompt_assembly.user_turn([], [], "hello", low_relevance=False)
    expected = (
        "[CONTEXT]\n(no relevant document content found)\n\n"
        "[HISTORY]\n(no prior turns)\n\n"
        "[QUESTION]\nhello"
    )
    assert turn == expected


def test_history_window_is_last_six_turns():
    long_history = [{"role": "user", "content": f"turn {i}"} for i in range(10)]
    turn = prompt_assembly.user_turn([], long_history, "q", low_relevance=False)
    history_block = turn.split("[HISTORY]\n", 1)[1].split("\n\n[QUESTION]")[0]
    lines = history_block.splitlines()
    assert lines == [f"user: turn {i}" for i in range(4, 10)]


def test_build_messages_shape():
    messages = prompt_assembly.build_messages(_CHUNKS, _HISTORY, _QUESTION, low_relevance=False)
    assert [m["role"] for m in messages] == ["system", "user"]
    assert messages[0]["content"] == prompt_assembly.system_prompt()
    assert messages[1]["content"] == prompt_assembly.user_turn(
        _CHUNKS, _HISTORY, _QUESTION, low_relevance=False
    )


def test_no_docs_message_matches_file():
    expected = (prompt_assembly._PROMPTS_DIR / "no_docs.md").read_text(encoding="utf-8").strip()
    assert prompt_assembly.no_docs_message() == expected
