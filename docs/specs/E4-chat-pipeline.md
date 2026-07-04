# SPEC E4 — Chat: prompt assembly, streaming answer, pipeline orchestrator

**Epic:** E4 · **Depends on:** E3 · **Architecture refs:** §3.2, §6, §7

## Objective
The full `POST /chat/stream` path: guardrail → history load → rewrite → retrieve →
streamed cited answer → background post-processing. After this epic the entire product
works end-to-end via curl.

## Deliverables
```
backend/pipeline/chat_pipeline.py    # the async orchestrator
backend/agents/answer_agent.py       # LiteLLM streaming + guard_stream wrap
backend/utils/prompt_assembly.py     # md modules + [CONTEXT]/[HISTORY]/[QUESTION] blocks
backend/services/history.py          # Redis last-6-turns load / append / TTL
backend/prompts/answerer_identity.md  citation_rules.md  no_docs.md
backend/api/chat.py                  # SSE endpoint + rate limit
backend/tests/ (pipeline, answer_agent, prompt_assembly, history, chat API)
```

## Requirements
1. **Pipeline order is law** (§3.2): guardrail first (zero LLM on the blocked path —
   test asserts no router call), then no-docs check (canned `no_docs.md` response, no
   LLM), then rewrite → [route=direct skips embed+retrieve] → retrieve → answer →
   BackgroundTasks post-process. Linear async function, no framework.
2. **Prompt assembly** per §6: system = answerer_identity + citation_rules; user turn =
   numbered `[CONTEXT]` chunks with citation labels + `[HISTORY]` + `[QUESTION]`.
   Prompts are .md files — never Python strings. citation_rules.md must instruct:
   cite `[n]` after each factual claim; when `low_relevance` or the context doesn't
   answer, say the documents don't cover it and DO NOT invent; never mention chunks,
   context blocks, or internal machinery.
3. **Answer agent**: streams via router alias `answerer` (OpenRouter → Groq failover
   handled by LiteLLM). Stream is wrapped in `guard_stream()` from E1. SSE events:
   `{token, seq}` with monotonically increasing seq, heartbeat comment every 15s,
   then `{"event":"sources", "sources":[{n, doc_id, filename, pages, snippet(≤300
   chars), score}]}` — **only chunks whose [n] actually appears in the answer text are
   marked `cited:true`**, others `cited:false` — then `{"event":"done"}`.
   On mid-stream provider death after failover: emit `{"event":"error", "detail":
   "friendly message"}`, never a raw exception.
4. **History** (`dc:history:{session_id}`): LPUSH `{role, content, ts}` per turn,
   LTRIM 12, TTL 24h. Guardrail-blocked messages are NOT stored (never replayed into a
   prompt). route=direct answers ARE stored.
5. **Rate limit**: 25 questions/session/day via Redis INCR+EXPIRE; 429 with friendly
   JSON. Check runs before any LLM call.
6. Timeouts: rewrite 6s, answer first-token 20s; every failure path produces a valid SSE
   error event so the UI never hangs.

## Acceptance criteria
- End-to-end via curl against live services: upload sample.pdf, ask a real question →
  streamed tokens with `[n]` citations → sources event lists the right pages.
- Off-topic question ("who won the 2022 world cup?") → the answer says the documents
  don't cover it, sources marked uncited.
- "ignore your instructions…" → canned refusal, zero LLM calls logged.
- Kill the primary provider (bad OpenRouter key locally) → Groq serves the answer.

## Required tests
- pipeline: mocked agents — event order; guardrail path has zero router calls; no-docs
  path; direct route skips retrieval; blocked messages absent from history.
- prompt_assembly: golden test — fixed chunks/history/question → exact assembled prompt.
- answer_agent: mocked stream — seq monotonic, sources cited/uncited flags computed from
  answer text, mid-stream failure → error event.
- chat API: 429 after limit; SSE content-type and heartbeat present.
