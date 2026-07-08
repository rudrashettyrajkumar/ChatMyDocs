"""Answer agent — streamed, cited reply (ARCHITECTURE §3.2 step 5, §6; spec E4 Req 3).

Streams through the `answerer` gateway role (BYOK model or demo failover
chain, 20s first-token timeout — gateway.ROLE_TIMEOUTS), wrapped in
`guardrails.guard_stream()` so a leaked prompt-block marker cuts the stream
before it reaches the client (E1's output rail).

Unlike every other agent in this codebase, this module does NOT catch and
degrade its own failures: by the time a mid-stream error happens, tokens may
already have reached the client, so there is no "safe default" to substitute —
the failure must propagate to `chat_pipeline`, which turns it into the one SSE
`error` event (same "errors degrade, never break" contract, enforced one layer
up).
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator

from backend.agents.retrieval_agent import RetrievedChunk
from backend.llm import gateway
from backend.llm.runconfig import DEFAULT, RunConfig
from backend.utils import prompt_assembly
from backend.utils.guardrails import guard_stream

# Matches citation markers the model emits inline, e.g. "...30 days [1][3]."
_CITATION_RE = re.compile(r"\[(\d+)\]")


def stream_answer(
    chunks: list[RetrievedChunk],
    history: list[dict[str, str]],
    question: str,
    low_relevance: bool,
    cfg: RunConfig = DEFAULT,
) -> AsyncIterator[str]:
    """Guarded answer token stream for the assembled prompt (spec Req 2/3).

    Any gateway/provider failure or `GuardrailTripped` propagates to the caller.
    """
    messages = prompt_assembly.build_messages(chunks, history, question, low_relevance)
    return guard_stream(gateway.stream("answerer", messages, cfg))


def _pages(chunk: RetrievedChunk) -> str:
    """`"14"` or `"14-16"` for a chunk spanning pages — the `sources` event's
    `pages` field (spec Req 3), distinct from the prompt's `citation_label`."""
    if chunk.page_start == chunk.page_end:
        return str(chunk.page_start)
    return f"{chunk.page_start}-{chunk.page_end}"


def cited_sources(chunks: list[RetrievedChunk], answer_text: str) -> list[dict[str, object]]:
    """The `sources` SSE event payload (spec Req 3).

    `cited` is true only for chunks whose `[n]` actually appears in the final
    answer text — a citation number the model never used stays `cited: false`
    rather than being dropped, so the UI can still show it dimmed.
    """
    cited_numbers = {int(m) for m in _CITATION_RE.findall(answer_text)}
    return [
        {
            "n": chunk.n,
            "doc_id": chunk.doc_id,
            "filename": chunk.filename,
            "pages": _pages(chunk),
            "snippet": chunk.text[:300],
            "score": chunk.score,
            "cited": chunk.n in cited_numbers,
        }
        for chunk in chunks
    ]
