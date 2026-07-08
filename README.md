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

It also answers the *second* question a cautious client asks — *"do I have to hand my
documents and my API bill to someone else?"* — with **Bring Your Own Key**: pick any
provider (a free one or your own paid account), paste your key, and it stays in your
browser. Or click **Demo mode** and try it with zero setup on free open-source models.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  FRONTEND — React (Vite + Tailwind) on Cloudflare Pages (free)   │
│  Dropzone upload · ingest progress · SSE chat · citations panel  │
│  Model Studio: pick a provider + model, bring your own key       │
└───────────────────────────┬──────────────────────────────────────┘
                            │ HTTPS + SSE  (BYOK key rides per-request
                            │               in a header, never stored)
┌───────────────────────────▼──────────────────────────────────────┐
│  BACKEND — FastAPI on Railway · email/password auth · HS256 JWT  │
│  LangGraph pipeline: guardrail → rewrite → retrieve → rerank →   │
│  streamed, cited answer   (LangChain is the one LLM layer)        │
└───┬───────────────┬───────────────┬───────────────┬──────────────┘
    │               │               │               │
┌───▼────────┐ ┌────▼─────┐ ┌───────▼────┐ ┌────────▼────────┐
│ LangChain  │ │ FlashRank│ │   Qdrant   │ │  Upstash Redis  │
│ providers: │ │ reranker │ │   Cloud    │ │ (chat history · │
│ Groq/OpenR.│ │(~4MB ONNX│ │ (768-dim,  │ │  users · rate   │
│ /OpenAI/   │ │ CPU, RRF │ │  one space │ │  limits)        │
│ Claude/Gem.│ │ fallback)│ │ per tenant)│ │                 │
└────────────┘ └──────────┘ └────────────┘ └─────────────────┘
```

PDF → PyMuPDF parse (in memory, nothing touches disk) → token-aware chunking →
batched embeddings → Qdrant. A question is rewritten into 2–4 standalone search
queries, retrieved and fused with **Reciprocal Rank Fusion (RRF)**, reranked by a
small open-source cross-encoder, then answered token-by-token with citations.

## Engineering highlights

- **Bring Your Own Key, multi-provider** — one LangChain layer (`ChatOpenAI` covers
  Groq/OpenRouter/OpenAI via a base-URL swap, plus `ChatAnthropic` and
  `ChatGoogleGenerativeAI`) puts five providers behind one interface. The user's key
  lives only in their browser and travels per-request in a header — it is **never
  written to a database, a log, or Redis**. No key? Demo mode runs on free
  open-source models on the server's own free-tier keys.
- **RRF multi-query retrieval + open-source reranking** — the rewriter expands one
  question into 2–4 standalone queries (so a follow-up like "what about page 5?" still
  retrieves correctly); their results are fused with Reciprocal Rank Fusion, then a
  ~4MB FlashRank cross-encoder (ONNX, CPU) reorders the top candidates. If the
  reranker model can't load, retrieval degrades to plain RRF order rather than failing.
- **LangGraph pipeline that degrades, never breaks** — guardrail → rewrite → retrieve
  → rerank → answer is a small state graph; every external call has a timeout and a
  fallback, and if a step fails the user still gets a valid streamed answer or a clean
  error, never a hang or a raw stack trace. The same nodes run sequentially if
  LangGraph itself is unavailable.
- **SSE hardening** — heartbeats keep idle connections alive through Railway's proxy,
  monotonic sequence IDs on every token let a client detect gaps, and every failure
  mode (guardrail block, LLM timeout, embedding failure) resolves to a valid terminal
  SSE event.
- **Injection/jailbreak guardrail** — a zero-cost regex rail runs *before* any model
  call; a blocked message never reaches an LLM and is never written to chat history,
  so a prompt-injection attempt can't poison future turns.
- **Session isolation + orphan cleanup** — every Qdrant search carries a tenant filter
  keyed on the authenticated account, enforced at one choke point with a test asserting
  it, so one user can never see another's documents. One embedding *space* per tenant
  is pinned on first upload (768-dim across every provider via Matryoshka truncation),
  and a daily job sweeps any ingestion that crashed before it was recorded against an
  account.

## Measured, not made up

Measured against the v3 build with `sample.pdf` (15 pages / 25 chunks), **demo mode**
(free NVIDIA Nemotron models via OpenRouter — the slowest path; a fast key like Groq
or GPT-4o-mini returns quicker):

| Metric | Measured value |
|---|---|
| Ingest (upload → searchable) | **~5s** |
| Time-to-first-token (question → first streamed word) | **~5s median** |

The first token includes the full rewrite → retrieve → rerank pre-work; the answer
then streams to completion in ~1–2s more. Free-tier providers occasionally spike
(one run hit ~15s) — the honest tradeoff for zero-setup demo access, and exactly why
BYOK exists. Re-run against production yourself: `./scripts/smoke.sh <backend-url>`
prints the live upload/chat timeline.

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

Tests: `.venv/bin/pytest` (191 tests, all mocked — no live API calls) and
`.venv/bin/ruff check .`.

## Limitations & next steps

- **No OCR** — scanned/image-only PDFs are rejected with a clear message, not silently
  mis-parsed. Real OCR (e.g. an external service) is a natural v2 add.
- **English-tuned** — the chunker and prompts aren't tuned for other languages yet.
- **Demo mode is free-tier speed** — the keyless demo runs on free open-source models
  and inherits their rate limits and occasional latency spikes. Bringing your own key
  (Groq's free tier, or any paid provider) is the fix, and the UI nudges you there when
  the free tier is slow.
- **One embedding space per account** — because query and document vectors must match,
  the embedding model is pinned on first upload; switching it means clearing your
  documents first (the app explains this rather than silently corrupting retrieval).

## Stack

FastAPI · LangChain + LangGraph · FlashRank reranker · Qdrant Cloud (768-dim) ·
Upstash Redis · PyMuPDF · React 18 + Vite + Tailwind + Motion · Railway ·
Cloudflare Pages. BYOK providers: Groq · OpenRouter · OpenAI · Anthropic · Gemini.
Full design: `docs/ARCHITECTURE.md`. Case study for the non-technical version:
`docs/CASE-STUDY.md`.
