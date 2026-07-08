# DocChat — Chat with your PDFs, with real citations

Upload a PDF, ask a question, get a streamed answer with **page-level citations** —
click one and it opens the exact passage it came from. Built to answer the question
every non-technical client actually has about "AI chatbots for my documents": *how do
I know it isn't making this up?*

**🔗 Live demo:** https://docchat-98q.pages.dev
**⚙️ API:** https://docchat-backend-production-e642.up.railway.app/health

![DocChat: upload a PDF, ask a question, get a cited answer](docs/demo.gif)
*(upload → streamed answer → click a citation to see the source passage)*

---

## Why this exists

Most "chat with your PDF" demos either hallucinate confidently or dodge every
question with "I don't have enough information." DocChat is built around one rule:
**every claim in an answer carries a `[n]` citation back to a real chunk of the
source document**, and when the documents genuinely don't cover a question, it says
so instead of guessing.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  FRONTEND — React (Vite + Tailwind) on Cloudflare Pages (free)  │
│  Dropzone upload · ingest progress · SSE chat · citations panel │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTPS + SSE
┌──────────────────────────▼──────────────────────────────────────┐
│  BACKEND — FastAPI on Railway (plain Python asyncio, no        │
│  LangChain) · email/password auth · own HS256 JWT               │
└───┬──────────────┬──────────────┬──────────────┬────────────────┘
    │              │              │              │
┌───▼──────┐ ┌─────▼───┐ ┌────────▼───┐ ┌────────▼────────┐
│OpenRouter│ │  Groq   │ │   Qdrant   │ │  Upstash Redis  │
│(LLM +    │ │(failover│ │   Cloud    │ │ (chat history + │
│ embed)   │ │provider)│ │  (free)    │ │  rate limits)   │
└──────────┘ └─────────┘ └────────────┘ └─────────────────┘
```

PDF → PyMuPDF parse (in memory, nothing touches disk) → token-aware chunking →
batched embeddings → Qdrant. A question goes through a lightweight rewrite step,
multi-query retrieval fused with **Reciprocal Rank Fusion (RRF)**, then a streamed,
citation-grounded answer.

## Engineering highlights

- **RRF multi-query retrieval** — the rewriter expands one question into 2–4
  standalone search queries (handles follow-ups like "what about page 5?"), and
  their results are fused with Reciprocal Rank Fusion rather than picked from a
  single top-k — meaningfully more robust than naive single-query retrieval.
- **SSE hardening** — heartbeats keep idle connections alive through proxies,
  monotonic sequence IDs on every token so a client can detect gaps, and every
  failure mode (guardrail block, LLM timeout, embedding failure) resolves to a
  valid terminal SSE event, never a hung connection or a raw stack trace.
- **Provider failover** — every LLM/embedding call routes through OpenRouter first
  and Groq on failure (LiteLLM Router), with a hard timeout so a slow upstream
  degrades the answer, never the request.
- **Injection/jailbreak guardrail** — a zero-cost regex rail runs *before* any
  model call; a blocked message never reaches an LLM and is never written to
  chat history, so a prompt-injection attempt can't poison future turns.
- **Session isolation + orphan cleanup** — every Qdrant search carries a
  tenant filter keyed on the authenticated account, so one user can never see
  another's documents; a daily job sweeps any ingestion that crashed before it
  could be recorded against an account, so failed uploads never leak as
  permanent, invisible storage.

## Measured, not made up

Measured against the live Railway deployment (`sample.pdf`, 15 pages / 25 chunks):

| Metric | Measured value |
|---|---|
| Ingest time (upload → searchable) | **~4.2s** |
| Time-to-first-token (question → first streamed word) | **~4.2s** |

(Re-run yourself: `./scripts/smoke.sh <backend-url>` prints the live upload/chat
timeline; see `docs/CASE-STUDY.md` for the measurement method.)

## Local setup

**Prerequisites:** Python 3.12, Node 18+, and a `.env` with real credentials (see
`.env.example` — OpenRouter, Groq, Qdrant Cloud, and Upstash Redis all have free
tiers this project fits inside).

```bash
# Backend
cd DocChat
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn backend.main:app --reload --port 8000
# → curl http://localhost:8000/health

# Frontend
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

Tests: `.venv/bin/pytest` (152 tests, all mocked — no live API calls) and
`.venv/bin/ruff check .`.

## Limitations & next steps

- **No OCR** — scanned/image-only PDFs are rejected with a clear message, not
  silently mis-parsed. Real OCR (e.g. an external service) is a natural v2 add.
- **English only** — the chunker and prompts aren't tuned for other languages yet.
- **No reranker** — retrieval quality comes from RRF fusion over multiple
  rewritten queries, not a cross-encoder reranking pass. Works well at this
  document scale; a reranker would be the next lever for larger corpora.
- **No LangChain/agent framework** — a deliberate choice (see
  `docs/CASE-STUDY.md`), not a limitation, but worth calling out for anyone
  expecting one.

## Stack

FastAPI · Qdrant Cloud · Upstash Redis · LiteLLM (OpenRouter → Groq) ·
`gemini-embedding-001` · PyMuPDF · React 18 + Vite + Tailwind · Railway ·
Cloudflare Pages. Full design: `docs/ARCHITECTURE.md`. Case study for the
non-technical version: `docs/CASE-STUDY.md`.
