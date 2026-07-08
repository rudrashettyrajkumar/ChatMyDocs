"""rewrite_agent tests (spec E3 Required tests): mocked LLM — valid JSON
parsed; malformed JSON/timeout -> safe default; history correctly included
in the prompt.
"""

import json
from unittest.mock import AsyncMock, patch

from backend.agents.rewrite_agent import rewrite


def _mock_complete(content: str) -> AsyncMock:
    # gateway.complete returns the reply TEXT (v3), not a response object.
    return AsyncMock(return_value=content)


async def test_valid_json_is_parsed():
    payload = json.dumps(
        {"route": "full", "queries": ["standalone query one", "standalone query two"]}
    )
    with patch(
        "backend.agents.rewrite_agent.gateway.complete", _mock_complete(payload)
    ):
        result = await rewrite("what about clause 5?", history=[], filenames=["msa.pdf"])

    assert result.route == "full"
    assert result.queries == ["standalone query one", "standalone query two"]


async def test_valid_json_strips_markdown_fence():
    payload = "```json\n" + json.dumps({"route": "direct", "queries": []}) + "\n```"
    with patch(
        "backend.agents.rewrite_agent.gateway.complete", _mock_complete(payload)
    ):
        result = await rewrite("hey there", history=[], filenames=[])

    assert result.route == "direct"
    assert result.queries == []


async def test_malformed_json_falls_back_to_safe_default():
    with patch(
        "backend.agents.rewrite_agent.gateway.complete",
        _mock_complete("not valid json{{{"),
    ):
        result = await rewrite("what does section 3 say?", history=[], filenames=[])

    assert result.route == "full"
    assert result.queries == ["what does section 3 say?"]


async def test_missing_field_falls_back_to_safe_default():
    payload = json.dumps({"route": "full"})  # missing `queries`
    with patch(
        "backend.agents.rewrite_agent.gateway.complete", _mock_complete(payload)
    ):
        result = await rewrite("summarize page 2", history=[], filenames=[])

    assert result.route == "full"
    assert result.queries == ["summarize page 2"]


async def test_full_route_with_out_of_range_query_count_falls_back():
    payload = json.dumps({"route": "full", "queries": ["only one query"]})
    with patch(
        "backend.agents.rewrite_agent.gateway.complete", _mock_complete(payload)
    ):
        result = await rewrite("tell me about the refunds policy", history=[], filenames=[])

    assert result.route == "full"
    assert result.queries == ["tell me about the refunds policy"]


async def test_timeout_falls_back_to_safe_default():
    async def _raise(*args, **kwargs):
        raise TimeoutError("rewriter timed out")

    with patch("backend.agents.rewrite_agent.gateway.complete", _raise):
        result = await rewrite("what is the notice period?", history=[], filenames=[])

    assert result.route == "full"
    assert result.queries == ["what is the notice period?"]


async def test_empty_question_falls_back_to_broad_query():
    with patch(
        "backend.agents.rewrite_agent.gateway.complete", _mock_complete("garbage")
    ):
        result = await rewrite("   ", history=[], filenames=[])

    assert result.queries == ["What does the document say?"]


async def test_history_is_included_in_the_prompt():
    complete_mock = _mock_complete(
        json.dumps({"route": "full", "queries": ["q1", "q2"]})
    )
    history = [
        {"role": "user", "content": "What is the termination notice period?"},
        {"role": "assistant", "content": "30 days' written notice [1]."},
    ]
    with patch("backend.agents.rewrite_agent.gateway.complete", complete_mock):
        await rewrite("what about clause 5?", history=history, filenames=["msa.pdf"])

    messages = complete_mock.await_args.args[1]
    user_content = messages[1]["content"]
    assert "What is the termination notice period?" in user_content
    assert "30 days' written notice [1]." in user_content
    assert "msa.pdf" in user_content
    assert "what about clause 5?" in user_content


async def test_direct_route_allows_empty_queries():
    payload = json.dumps({"route": "direct", "queries": []})
    with patch(
        "backend.agents.rewrite_agent.gateway.complete", _mock_complete(payload)
    ):
        result = await rewrite("thanks!", history=[], filenames=[])

    assert result.route == "direct"
    assert result.queries == []
