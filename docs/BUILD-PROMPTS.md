# BUILD PROMPTS — one Claude Code session per epic

How to use: open a fresh Claude Code session in the DocChat repo, paste the prompt for
the current epic, review the result, run the tests, then `/spec-check` before committing.
Don't start the next epic in the same session — fresh context per epic keeps quality high.

> Prompts deliberately point at the spec + architecture instead of repeating details.
> The docs are the source of truth; the prompt's job is scope + guardrails + definition
> of done.

---

## E1 — Foundation

```
Read docs/ARCHITECTURE.md fully, then implement docs/specs/E1-foundation.md exactly.

Context: this is a portfolio RAG demo that generalizes patterns from my MyShiva project.
Where the spec says "port from MyShiva", the reference implementations are in
/mnt/d/PortfolioProjects/MyShiva/backend/utils/ (llm_router.py, guardrails.py, sse.py,
config.py) — read them and adapt: strip Shiva/crisis/persona specifics, keep the
engineering (failover chain, semaphore, guard_stream, env-driven config).

Hard rules:
- No LangChain/LangGraph/agent frameworks. Plain Python 3.12 asyncio + FastAPI + LiteLLM.
- Every model ID, key, and limit comes from backend/utils/config.py env vars.
- Every external call: timeout + fallback. Errors degrade, never break.
- Tests mock all external services (conftest fixtures); ruff clean.

Definition of done: everything under "Acceptance criteria" and "Required tests" in the
spec. Run pytest and ruff yourself before declaring done. If the spec is ambiguous, make
the smallest reasonable choice and flag it in your summary.
```

---

## E2 — Ingestion

```
Read docs/ARCHITECTURE.md §3.1/§5.1/§5.2 and implement docs/specs/E2-ingestion.md exactly.
E1 is already merged — reuse its config, clients, sse helpers; don't reinvent them.

Priorities in order: (1) chunker correctness — page tracking through splits and overlaps
is the most bug-prone part, write its golden test FIRST; (2) validation/limit rejections
with friendly errors; (3) rollback on mid-ingestion failure (no half-ingested docs);
(4) SSE progress events matching the spec's exact shapes (the frontend will bind to them).

Also download a suitable public-domain PDF (10–30 pages, text-heavy) into sample/sample.pdf
and note its source in the commit body.

Hard rules: PDF stays in memory (never written to disk); point payloads exactly per
ARCHITECTURE §5.1; doc_id is server-generated. Tests mock embed/Qdrant/Redis; ruff clean.
Done = spec's acceptance criteria + required tests green.
```

---

## E3 — Retrieval

```
Read docs/ARCHITECTURE.md §3.2 (steps 2–4), §5.3, §5.4 and implement
docs/specs/E3-retrieval.md exactly. E1+E2 are merged.

Port utils/rrf.py verbatim from /mnt/d/PortfolioProjects/MyShiva/backend/utils/rrf.py and
model rewrite_agent's failure handling on MyShiva's DEFAULT_DETECTION pattern
(backend/agents/detection_agent.py there): any parse error or timeout → safe default,
never an exception.

Two things I will personally check, get them right:
1. The session_id filter is applied at ONE choke point inside retrieval_agent and a test
   asserts it is present on every Qdrant search call.
2. The eval harness (scripts/eval_retrieval.py + 15 hand-written questions about
   sample.pdf with expected pages) runs against live Qdrant and reports ≥12/15. Write
   thoughtful eval questions: mix of factual lookup, synthesis across sections, and one
   deliberately-unanswerable question to observe scores for threshold calibration.

Done = acceptance criteria + required tests + eval_report.md committed.
```

---

## E4 — Chat pipeline

```
Read docs/ARCHITECTURE.md §3.2 and §6 and implement docs/specs/E4-chat-pipeline.md
exactly. E1–E3 merged; compose their pieces, don't duplicate them.

The pipeline order in §3.2 is law: guardrail → no-docs check → rewrite → (direct skips
retrieval) → retrieve → streamed answer → BackgroundTasks. Write the pipeline test that
asserts ZERO llm-router calls on the guardrail path before writing the pipeline itself.

Prompt files (answerer_identity.md, citation_rules.md) are product-critical: the answer
must cite [n] per claim, refuse gracefully on low_relevance, and never mention chunks or
internal machinery. Keep them concise — under ~300 words each.

The SSE event contract in the spec (token/seq, sources with cited flags, done, error) is
frozen — E5's frontend binds to it. After implementing, verify end-to-end with curl
against live services per the acceptance criteria and paste the transcript in your
summary. Done = acceptance criteria + required tests green.
```

---

## E5 — Frontend

```
Implement docs/specs/E5-frontend.md exactly. Read docs/ARCHITECTURE.md §7 and §8 first,
and read backend/api/chat.py + documents.py + backend/utils/sse.py to bind to the REAL
SSE event shapes — do not guess the contract.

Stack: Vite + React 18 + TypeScript + Tailwind. No component library. react-markdown for
answers. SSE via fetch streaming (POST bodies rule out EventSource) — parse frames
manually in api/client.ts.

Build in the spec's task order (shell → upload → chat → citations → resilience → polish)
and keep it working at every step against the live local backend (npm run dev +
uvicorn). This screen IS the portfolio: spend the effort on streaming smoothness,
citation chip → sources drawer interaction, and the error/empty/limit states. Dark
theme default, mobile-usable, OG tags.

Done = the spec's acceptance checklist, walked through personally in an incognito
window, including the devtools-offline reconnect test.
```

---

## E6 — Ship

```
Implement docs/specs/E6-ship.md. Everything is built; this session makes it live and
turns it into a portfolio asset.

Order: cleanup script + workflow (test with a manual dispatch against seeded expired
points) → Railway deploy (second service, existing project — verify SSE through the
proxy with a real streamed chat) → Cloudflare Pages deploy + CORS lock → smoke.sh
against prod → UptimeRobot → README → CASE-STUDY.md → LOOM-SCRIPT.md.

For the README and case study: audience is a non-technical client skimming an Upwork
profile who fears hallucinating chatbots. Lead with the live demo link and the citation
GIF (give me the exact terminal command / steps to record it). Measure real numbers
(time-to-first-token, ingest seconds for sample.pdf) and put them in the README — no
made-up metrics.

Walk me through the Railway/Cloudflare/UptimeRobot dashboard steps you can't do yourself
as a numbered checklist, and do everything else autonomously. Done = smoke.sh green
against production + acceptance checklist.
```
