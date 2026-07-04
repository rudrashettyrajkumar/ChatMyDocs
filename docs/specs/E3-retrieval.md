# SPEC E3 — Retrieval: rewrite agent, filtered search, RRF, citations, eval harness

**Epic:** E3 · **Depends on:** E2 · **Architecture refs:** §3.2 steps 2–4, §5.3, §5.4

## Objective
Two agents: `rewrite_agent.py` (question + history → route + standalone English queries)
and `retrieval_agent.py` (queries → 6 numbered, citation-labeled chunks via batched embed
+ session-filtered Qdrant + RRF). Plus the retrieval eval harness that proves quality
before the chat pipeline is wired.

## Deliverables
```
backend/agents/rewrite_agent.py
backend/agents/retrieval_agent.py
backend/utils/rrf.py                     # ported verbatim from MyShiva
backend/prompts/rewriter.md
backend/scripts/eval_retrieval.py        # harness (not pytest)
backend/scripts/eval_questions.json      # 15 hand-written Q&A pairs for sample.pdf
backend/tests/ (rewrite_agent, retrieval_agent, rrf)
```

## Requirements
1. **Rewrite agent**: one call to alias `rewriter` (LiteLLM router from E1). Input:
   question, last 6 turns, session filenames. Output strict JSON
   `{route: "direct"|"full", queries: [2–4 standalone English strings]}`.
   Prompt in `prompts/rewriter.md` with 3 few-shot examples covering: a follow-up that
   needs history to become standalone, a greeting → direct, a multi-facet question → 3
   queries. **Any** parse error, missing field, or timeout → `{route:"full",
   queries:[question]}` (degraded beats broken — MyShiva DEFAULT_DETECTION pattern).
2. **Retrieval agent** per §5.4: one batched embed for all queries → parallel Qdrant
   searches with `must=[session_id]` filter applied inside this module at one choke
   point → RRF k=60 → dedup by point id → top 6.
3. Every returned chunk carries `citation_label` = `"{filename}, p.{page_start}"` (or
   `"p.{page_start}–{page_end}"` when spanning) and its 1-based citation number.
4. **Low-relevance flag**: best raw cosine < RELEVANCE_THRESHOLD → `low_relevance=True`
   on the result set (the answer prompt uses this to say the docs don't cover it).
5. Failure degrades: one query's search failing → proceed with the rest; all fail →
   empty chunks + flag, never an exception out of the agent.
6. **Eval harness**: ingests sample.pdf (idempotent), runs the 15 questions, prints top-3
   chunks + scores per question, writes `eval_report.md`, exits non-zero if <12/15
   questions have a relevant chunk in top-3 (hand-label relevance by expected page in
   eval_questions.json). Calibrate RELEVANCE_THRESHOLD here and commit the value.

## Acceptance criteria
- Eval harness passes ≥12/15 against live Qdrant; report committed once, reviewed by Raj.
- p95 retrieval latency (embed + search + RRF) < 600ms measured from the laptop.
- A search executed with session B's id returns zero of session A's chunks (isolation).

## Required tests
- rrf: hand-computed fixture (3 lists, known fused order), dedup across lists.
- rewrite_agent: mocked LLM — valid JSON parsed; malformed JSON/timeout → safe default;
  history correctly included in the prompt.
- retrieval_agent: mocked embed+Qdrant — session filter ALWAYS present in the search
  call (assert on the mock), partial failure degradation, low_relevance flag, citation
  numbering stable.
