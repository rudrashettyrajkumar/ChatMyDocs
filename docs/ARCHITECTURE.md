# DOCCHAT — SOLUTION DESIGN & TECHNICAL ARCHITECTURE
**v1.0 · July 4, 2026 · Budget: ₹0 extra/month (rides on existing free tiers + Railway Hobby) · Timeline: 1 week**

> ### ⚠️ v1.1 addendum (auth + account model) — supersedes the "anonymous session" design below
> DocChat now requires **login**. A self-contained **email/password** system (no external
> provider, still ₹0) replaces the anonymous localStorage session:
> - **Users** persist in Upstash (`dc:user:{email}` hash + `dc:userid:{id}` → email), passwords
>   hashed with stdlib **PBKDF2-HMAC-SHA256** (no bcrypt/passlib dependency). We mint our own
>   **HS256 JWT** (`JWT_SECRET`, `JWT_TTL_DAYS`, default 7) at register/login.
> - The **authenticated user id is the tenant key** everywhere the design says "session_id":
>   the Qdrant `session_id` payload filter, `dc:session:{id}:docs`, `dc:history:{id}`, and the
>   per-day rate counters all key on it. Cross-tenant isolation is unchanged in spirit.
> - **Persistence:** documents and chat history no longer carry a 24h TTL — they live with the
>   account until deleted. Only the per-day quota counters (`dc:qcount`, `dc:iplimit`) expire.
> - **API:** `POST /auth/register`, `POST /auth/login` → `{access_token, user}`; `GET /auth/me`.
>   Data routes take `Authorization: Bearer <jwt>` (the old `X-Session-Id` header is gone).
> - **Frontend:** react-router with `/` (landing), `/login`, `/register`, and a protected
>   `/app`; a light-first colorful **glassmorphism** UI with a dark-mode toggle
>   (see `docs/DESIGN-SYSTEM.md`). Everything below that mentions "anonymous / no auth / 24h
>   wipe" reflects v1.0 and is kept for provenance.

> Portfolio Project #1: "Chat with your documents." Upload PDFs → ask questions → get
> streamed answers **with page-level citations**. A generalized, open-source-able version
> of the MyShiva RAG pipeline. Target audience: Upwork/Fiverr clients evaluating whether
> Raj can build production RAG — so the demo must feel instant, cited, and unbreakable.

---

## 1. PRODUCT SUMMARY

DocChat is a live web demo: a visitor lands on the page, drags in up to 3 PDFs, waits a few
seconds while a progress bar shows parsing → chunking → embedding, then chats with their
documents. Every answer streams token-by-token and carries inline citations `[1] [2]` that
map to a sources panel showing the exact chunk text and page number. No signup, no login —
an anonymous session (UUID in localStorage) owns the documents, and everything is wiped
after 24 hours.

**What this demo is selling (the real product is Raj's skill):**

| Visible feature | Skill it proves |
|---|---|
| Cited answers, "I don't know" when the doc doesn't cover it | Grounded RAG, no hallucination |
| Token streaming with sub-2s first token | SSE, async pipeline design |
| Multi-query retrieval + RRF | Retrieval engineering beyond naive top-k |
| Prompt-injection guardrail ("ignore your instructions" → polite refusal) | Production safety thinking |
| Provider failover (OpenRouter → Groq) | Reliability engineering |
| Session isolation + 24h auto-cleanup | Multi-tenant data hygiene |

Differences from MyShiva (what was **removed** because a demo doesn't need it): persona
prompts, crisis filter, language detection, long-term memory, auth, quota tiers, payments.
What was **kept**: the entire retrieval core, SSE hardening, LiteLLM failover, guardrails,
graceful degradation, env-driven config.

---

## 2. SYSTEM OVERVIEW

```
┌─────────────────────────────────────────────────────────────────┐
│  FRONTEND — React (Vite + Tailwind) on Cloudflare Pages (free)  │
│  Dropzone upload · ingest progress · SSE chat · citations panel │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTPS + SSE
┌──────────────────────────▼──────────────────────────────────────┐
│  BACKEND — FastAPI on Railway Hobby (shares MyShiva's $5 plan)  │
│  Plain Python asyncio pipeline · LiteLLM Router · no auth       │
└───┬──────────────┬──────────────┬──────────────┬────────────────┘
    │              │              │              │
┌───▼──────┐ ┌─────▼───┐ ┌────────▼───┐ ┌────────▼────────┐
│OpenRouter│ │  Groq   │ │   Qdrant   │ │  Upstash Redis  │
│(LLM +    │ │(failover│ │   Cloud    │ │ (chat history + │
│ embed)   │ │provider)│ │  (free 1GB)│ │  rate limits)   │
└──────────┘ └─────────┘ └────────────┘ └─────────────────┘
```

Same design principle as MyShiva: **the container is stateless and featherweight.** No
local ML models, no local file storage (PDFs are parsed in memory and discarded — only
chunks + vectors persist, in Qdrant). Restarts are instant; scaling is trivial.

**No new infra accounts needed.** DocChat deploys as a second Railway service on the
existing Hobby plan, a second collection on the existing Qdrant cluster, and the existing
Upstash Redis with a `dc:` key prefix. Supabase is NOT used — there is no relational data
worth a database here; document metadata lives in Redis with the same 24h TTL as the chat.

---

## 3. THE TWO PIPELINES

### 3.1 Ingestion pipeline — `POST /documents` (multipart upload)

```
PDF arrives (validated: ≤10MB, ≤100 pages, ≤3 docs per session, PDF magic bytes)
  ↓
STEP 1 — PARSE (PyMuPDF, in-memory, ~1s for a 50-page PDF)
  Extract text per page. Reject scanned/image-only PDFs with a clear
  message ("This PDF has no extractable text") — no OCR in v1.
  ↓
STEP 2 — CHUNK (pure Python, token-aware)
  450-token chunks, 80-token overlap, split on paragraph boundaries
  where possible. Each chunk records page_start / page_end (chunks can
  span a page break) and chunk_index.
  ↓
STEP 3 — EMBED (batched, gemini-embedding-001 @ 768 dims via OpenRouter)
  Batches of 100 chunks per request. A 100-page PDF ≈ 150 chunks
  ≈ 2 requests.
  ↓
STEP 4 — UPSERT to Qdrant collection `docchat_chunks`
  payload: { session_id, doc_id, filename, page_start, page_end,
             chunk_index, text, created_at }
  ↓
Return { doc_id, filename, pages, chunks, status: "ready" }
```

The endpoint is **synchronous with streamed progress**: it returns SSE progress events
(`parsing` → `chunking` → `embedding 40%` → `ready`) so the UI shows a real progress bar.
Total time for a typical PDF: 3–8 seconds. No job queue — a queue is over-engineering at
this scale and the SSE progress stream is a better demo anyway.

Doc metadata (`doc:{doc_id}` hash: filename, pages, chunks, session_id) and the session's
doc list (`session:{session_id}:docs`) are stored in Redis, TTL 24h.

### 3.2 Chat pipeline — `POST /chat/stream`

```
User question arrives (with session_id)
  ↓
STEP 0 — INPUT GUARDRAIL (pure Python regex, zero API cost)
  Same pattern as MyShiva utils/guardrails.py: prompt injection /
  jailbreak / prompt-exfiltration scan. If triggered → canned polite
  refusal, no LLM call, message not stored in history. Pipeline ends.
  ↓
STEP 1 — CONTEXT LOAD (~30ms)
  Redis: last 6 turns of this session (key dc:history:{session_id})
  + the session's document list (filenames, for the rewriter's context).
  If the session has zero documents → canned "upload a document first"
  response, no LLM. Pipeline ends.
  ↓
STEP 2 — QUERY REWRITE (one small LLM call, ~400ms)
  Model: Flash-Lite via OpenRouter (LiteLLM Router, Groq fallback)
  Input: question + last 6 turns + list of uploaded filenames
  Output (strict JSON):
    { route: "direct" | "full",
      queries: ["standalone english query 1", "query 2", ...] }   # 2–4
  route=direct → greetings, thanks, "what did you just say?" —
    answered from history alone, retrieval skipped (steps 3–4).
  route=full  → normal RAG. Follow-up questions ("what about clause 5?")
    are rewritten into standalone queries using history.
  Any parse failure/timeout → DEFAULT: route=full,
    queries=[question verbatim]. Degraded beats broken.
  ↓
STEP 3 — EMBED (one batched call, ~200ms)
  All queries in a single gemini-embedding-001 request, 768 dims.
  ↓
STEP 4 — RETRIEVAL (~150ms)
  Parallel Qdrant searches, filter must=[session_id], top-8 per query
  → Reciprocal Rank Fusion (k=60) → dedup → top 6 chunks.
  Each chunk labeled: "[n] {filename}, p.{page_start}"
  Low-relevance flag: best raw cosine < RELEVANCE_THRESHOLD (env,
  default 0.30) → low_relevance=True.
  ↓
STEP 5 — ANSWER (streaming)
  Model: Flash via OpenRouter → Groq llama-3.3-70b fallback.
  Prompt (see §6): grounding rules + numbered chunks + history + question.
  Contract: cite as [n] after each claim; if low_relevance or the chunks
  don't answer it, SAY SO — "The documents don't cover this" — never
  invent content.
  Output: SSE token stream, heartbeat every 15s, sequence IDs.
  Output guardrail: guard_stream() cuts the stream if internal prompt
  markers ([CONTEXT]/[HISTORY]/…) start leaking.
  Final event: {"event":"sources"} carrying the cited chunks
  (id, filename, pages, text snippet, score) for the UI panel.
  ↓
STEP 6 — POST-PROCESS (FastAPI BackgroundTasks — never blocks)
  Redis: LPUSH turn → LTRIM 12 → TTL 24h. Increment rate counter.

Latency to first token: ~1.2–1.6s (one fewer LLM hop than MyShiva).
```

The orchestrator is one async function (`pipeline/chat_pipeline.py`) — linear, two
deterministic early exits (guardrail, no-docs), data-driven routing. **No agent framework**,
same as MyShiva. This is a deliberate portfolio talking point: "I know when NOT to use
LangChain."

---

## 4. MODEL STRATEGY

Identical gateway pattern to MyShiva: **OpenRouter primary, Groq failover**, everything
through LiteLLM Router with retries. Same OpenRouter account/key — the $10 top-up already
funds both apps.

| Role | Primary (via OpenRouter) | Fallback (Groq) | Notes |
|---|---|---|---|
| Query rewrite | `google/gemini-3.1-flash-lite-preview` | `llama-3.3-70b-versatile` | strict JSON out |
| Answer (streamed) | `google/gemini-3-flash-preview` | `llama-3.3-70b-versatile` | citations contract |
| Embeddings | `google/gemini-embedding-001` (768 dims) | — | queries + ingestion |

All model IDs are env vars via `backend/utils/config.py` — never hardcoded (MyShiva
invariant #2 carries over). Async semaphore caps concurrent LLM calls at 8.

**Demo-scale capacity math:** even a great week of portfolio traffic is ~50 sessions/day
× 5 questions = 250 turns/day → 500 LLM calls + 250 embed calls. Far inside limits; cost
≈ $0.50/month of the existing OpenRouter credit.

---

## 5. RAG DESIGN

### 5.1 One collection, payload-filtered multi-tenancy

```
Collection: docchat_chunks   (768 dims, cosine)
Payload:    session_id (keyword, indexed)   ← tenant isolation
            doc_id     (keyword, indexed)   ← per-doc delete
            created_at (float, indexed)     ← 24h cleanup
            filename, page_start, page_end, chunk_index, text
```

One collection with a **mandatory `session_id` filter on every search** — the standard
multi-tenant pattern (per-session collections would exhaust Qdrant free-tier limits and is
an anti-pattern anyway). The filter is applied inside `retrieval_agent.py` at one choke
point, not at call sites, so it cannot be forgotten.

Capacity: free 1GB cluster minus MyShiva's ~176MB leaves room for ~150K DocChat chunks
live at once; with 24h TTL cleanup the realistic steady state is <5K. Non-issue.

### 5.2 Chunking

450 tokens, 80 overlap (tiktoken `cl100k_base` for counting), preferring paragraph
boundaries, hard-splitting only oversized paragraphs. Page numbers tracked through the
split so citations stay honest. This mirrors MyShiva's per-corpus tuning philosophy —
one size chosen deliberately, documented, changeable via constants.

### 5.3 Retrieval

Multi-query (2–4 rewritten queries) → one batched embed call → parallel filtered searches
top-8 → RRF (k=60) → top 6. The `reciprocal_rank_fusion` implementation is lifted verbatim
from MyShiva `utils/rrf.py`. No cross-encoder reranker — same reasoning as MyShiva: RRF
over multi-query captures most recall benefit at zero latency/cost.

**Grounding rule (the demo's soul):** if best score < threshold or chunks don't contain
the answer, the model must say the documents don't cover it. The README will showcase this
with a screenshot — clients fear hallucinating bots more than they value fancy answers.

### 5.4 Citations (new vs MyShiva)

Chunks are numbered [1]..[6] in the prompt. The model cites inline. After the stream, a
`sources` SSE event delivers the chunk records; the UI renders citation chips → click →
sources panel highlights the chunk with filename + page. Uncited sources still appear,
dimmed. If the model emits a citation number with no matching chunk, the UI drops it
(post-process safety net).

---

## 6. PROMPT SYSTEM

Same discipline as MyShiva: prompts are `.md` files in `backend/prompts/`, assembled at
runtime, never Python strings.

```
System = answerer_identity.md   (concise, professional, grounded-only,
                                 markdown allowed — unlike Shiva's prose rule)
       + citation_rules.md      (cite [n] per claim; refuse gracefully when
                                 context is insufficient; never mention
                                 "chunks" or internal machinery to the user)

User turn = [CONTEXT] numbered labeled chunks
          + [HISTORY] last 6 turns
          + [QUESTION] user question

rewriter.md    — the query-rewrite JSON prompt (route + queries)
guardrails.md  — canned refusal for injection attempts
no_docs.md     — canned "please upload a document first"
```

---

## 7. API SPECIFICATION

Base: Railway URL (later `api.docchat.example`). No auth; `session_id` is a client-generated
UUID v4 sent as `X-Session-Id` header on every request.

```
POST /documents            multipart PDF → SSE progress events → final
                           {doc_id, filename, pages, chunks, status}
GET  /documents            → [{doc_id, filename, pages, chunks, uploaded_at}]
DELETE /documents/{doc_id} → {deleted: true}     (Qdrant delete by doc_id filter + Redis)
POST /chat/stream          {question} → SSE: {token, seq}… {event: sources}… {done}
GET  /health               → {status, qdrant, redis, llm}
```

**Rate limits (Redis, per session + per IP):** 3 documents/session, 25 questions/session/day,
10 uploads/IP/day. Exceeded → HTTP 429 with a friendly JSON message the UI renders nicely.
This is the demo's abuse shield since there's no auth.

---

## 8. FRONTEND (single screen, two panels)

React 18 + Vite + Tailwind on Cloudflare Pages. No component library bloat — this page IS
the portfolio piece.

```
┌────────────────────┬──────────────────────────────────────┐
│  SIDEBAR           │  CHAT                                │
│  ┌──────────────┐  │  message list (user / assistant)     │
│  │  Dropzone    │  │  streamed tokens render live         │
│  │  drag PDF or │  │  citation chips [1] [2] inline       │
│  │  click       │  │                                      │
│  └──────────────┘  │  ┌────────────────────────────────┐  │
│  doc cards:        │  │ SOURCES drawer (per answer):   │  │
│   name, pages,     │  │ [1] report.pdf · p.14          │  │
│   chunk count, ✕   │  │     "…exact chunk text…"       │  │
│  ingest progress   │  └────────────────────────────────┘  │
│  bar during upload │  input box · disabled until ≥1 doc   │
│  "Try sample PDF"  │  suggested starter questions         │
└────────────────────┴──────────────────────────────────────┘
```

Key UX rules (mirrors MyShiva's resilience UX):
- SSE reconnect with `Last-Event-ID`, exponential retry 1s/2s/4s/8s; never a raw error.
- **"Try a sample PDF" button** — preloads a bundled public PDF so a client with no file
  handy sees the demo in one click. This single button is the highest-conversion feature.
- Session persists in localStorage; a "documents expire after 24h" note sets expectations.
- Empty/error/limit states all designed, not default browser text.

---

## 9. INFRASTRUCTURE & OPS

| Layer | Service | Plan | Cost | Notes |
|---|---|---|---|---|
| Backend | Railway (2nd service, same project) | Hobby (existing) | ₹0 extra while usage stays in credit | featherweight container |
| Vectors | Qdrant Cloud (existing cluster) | Free | ₹0 | new collection `docchat_chunks` |
| Cache/limits | Upstash Redis (existing) | Free | ₹0 | `dc:` key prefix, TTL 24h everywhere |
| Frontend | Cloudflare Pages | Free | ₹0 | |
| LLM/embed | OpenRouter (existing credit) + Groq | — | ≈$0.50/mo | |
| Monitoring | UptimeRobot | Free | ₹0 | /health every 5 min |

**Cleanup cron (GitHub Actions, daily):** `scripts/cleanup_expired.py` deletes Qdrant
points where `created_at < now − 24h` (Redis keys expire on their own via TTL). Reuses
MyShiva's keepalive-cron pattern; the same workflow doubles as the Qdrant keepalive.

**Config:** all keys/models/limits via `backend/utils/config.py` from env vars; `.env`
gitignored, `.env.example` committed blank. Same as MyShiva.

---

## 10. REPOSITORY STRUCTURE

```
docchat/
├── .github/workflows/cleanup.yml       # daily TTL cleanup + keepalive
├── docs/
│   ├── ARCHITECTURE.md                 ← this file
│   ├── BUILD-PROMPTS.md                # one Claude Code prompt per epic
│   └── specs/                          # E1..E6, one per epic
├── backend/
│   ├── main.py
│   ├── pipeline/chat_pipeline.py       # async orchestrator (§3.2)
│   ├── agents/
│   │   ├── rewrite_agent.py            # route + multi-query JSON
│   │   ├── retrieval_agent.py          # embed + filtered Qdrant + RRF
│   │   └── answer_agent.py             # LiteLLM stream + citations
│   ├── ingestion/
│   │   ├── parser.py                   # PyMuPDF page extraction
│   │   ├── chunker.py                  # token-aware, page-tracking
│   │   └── ingest_service.py           # orchestrates parse→chunk→embed→upsert
│   ├── utils/
│   │   ├── config.py  llm_router.py  guardrails.py  rrf.py
│   │   ├── qdrant_client.py  redis_client.py  sse.py  embeddings.py
│   ├── prompts/  (answerer_identity, citation_rules, rewriter,
│   │              guardrails, no_docs — all .md)
│   ├── api/  (documents.py  chat.py  health.py)
│   ├── middleware/rate_limit.py
│   ├── scripts/  (cleanup_expired.py  eval_retrieval.py)
│   └── tests/    (mirrors module paths; external services mocked)
├── frontend/                            # Vite + React + Tailwind
│   └── src/  (components/ hooks/ api/ lib/)
├── sample/sample.pdf                    # the "try it" document
├── Dockerfile  requirements.txt  .env.example  README.md  CLAUDE.md
```

---

## 11. EPICS (build order)

| Epic | Name | Side | Depends on |
|---|---|---|---|
| **E1** | Foundation — skeleton, config, clients, router, guardrails, health | Backend | — |
| **E2** | Ingestion — upload → parse → chunk → embed → upsert, progress SSE, limits | Backend | E1 |
| **E3** | Retrieval — rewrite agent, RRF, citations labels, eval harness | Backend | E2 |
| **E4** | Chat — prompt assembly, answer stream, pipeline, history, rate limits | Backend | E3 |
| **E5** | Frontend — upload UX, streaming chat, citations panel | UI | E4 (API contract from E1–E4) |
| **E6** | Ship — deploy, cleanup cron, README, sample PDF, Loom script, case study | DevOps/Polish | E5 |

One epic per Claude Code session. Every spec ends with acceptance criteria + required
tests; a feature is DONE only when tests pass and `/spec-check` passes.

Suggested week: Day 1 E1 · Day 2 E2 · Day 3 E3 · Day 4 E4 · Day 5–6 E5 · Day 7 E6.

---

## 12. QUALITY BAR (portfolio non-negotiables)

1. Guardrail runs before any LLM call; injection attempts never reach a model. Tested.
2. Every Qdrant search carries the session filter. A test asserts cross-session leakage
   is impossible.
3. Every external call has timeout + fallback; the user always gets a response.
4. "I don't know" behavior verified with an off-topic question against the sample PDF.
5. Zero secrets in the repo; `.env.example` complete.
6. README has: live demo link, 60-second architecture diagram, GIF of the citation UX,
   "how it's built" section, and honest limitations list.

---

## 13. v3 ADDENDUM — BYOK MULTI-PROVIDER + LANGCHAIN/LANGGRAPH (2026-07-08)

Raj-requested overhaul; **supersedes §4's LiteLLM design and the v1 "no frameworks"
lock**. Everything below is implemented on top of the v1.1 auth architecture.

### 13.1 Bring-Your-Own-Key (BYOK)
Users pick a provider + chat model + (optionally) embedding model in the frontend
"Model Studio" and paste their own API key. **Keys never touch server storage**:
they live in localStorage and ride each request as headers —
`X-LLM-Provider/-Model/-Key` (chat) and `X-Embed-Provider/-Model/-Key`
(embeddings) — parsed and validated once per request in `backend/llm/runconfig.py`
(bad input → 400 `byok_invalid` BEFORE any stream commits).

- **No headers → demo mode**: an env-driven two-provider chain on the server's keys,
  with the existing daily quotas (the ₹0 story is untouched). **Demo mode serves ONLY
  free-tier OPEN-SOURCE models** (verified working July 2026), split by each provider's
  strengths:
  - **Chat** (rewriter + answerer) on **Groq's Llama 3.3 70B** — LPU-fast, a reliable
    citer (verified 6/6 vs flaky free reasoning models), and Groq's free tier is
    ~1000 req/day/model vs OpenRouter's ~200/day.
  - **Embeddings** on **OpenRouter's NVIDIA `llama-nemotron-embed-vl-1b-v2:free`**
    ($0, Matryoshka 768-dim) — OpenRouter's scarce free tier is reserved for
    embeddings, its unique capability here (Groq has no embedding model).
  - **Diverse fallback**: each chat role fails over to the *other* free provider
    (Groq↔OpenRouter Nemotron `:free`), so a rate-limit or outage on one degrades to
    the other. `factory.demo_chain` builds this ordered chain.
  Never a paid/proprietary model. When the free tier saturates, error messages say so
  and point users at BYOK. (An earlier v3 iteration ran chat on OpenRouter Nemotron;
  live testing showed it cited unreliably and OpenRouter's 200/day cap is tight, so
  chat moved to Groq.)
- **BYOK gets no server fallback** — a broken user key fails with a fixable,
  provider-naming error event, never silently burns demo credit.

### 13.2 Provider catalog (`backend/llm/catalog.py`, served at `GET /api/models`)
Five providers: **Groq** (free tier, LPU-fast Llama/GPT-OSS/Qwen), **OpenRouter**
(one key → 400+ models incl. rotating `:free` open-source tier; custom model ids
allowed), **OpenAI** (GPT-5.x/4.1/4o-mini), **Anthropic** (Claude Fable 5 → Haiku
4.5 — top accuracy tier), **Gemini** (3.5 Flash etc., free AI Studio keys). Each
model carries a 1-5 accuracy tier, speed/cost/context labels, and each provider
carries step-by-step "get a key" instructions rendered verbatim by the UI.
`POST /api/models/validate` makes one live ping so the UI can prove a key works.

### 13.3 LangChain + LangGraph layer (replaces LiteLLM everywhere)
- `backend/llm/factory.py` — the ONLY module importing provider SDKs (lazily):
  `ChatOpenAI` covers OpenRouter/Groq/OpenAI via `base_url`; `ChatAnthropic`,
  `ChatGoogleGenerativeAI` cover the rest.
- `backend/llm/gateway.py` — the single agent-facing chokepoint (`complete`/
  `stream`), keeping v1's semaphore + role timeouts + failover-chain semantics.
- `backend/graph/chat_graph.py` — the turn as a StateGraph:
  `guardrail → context → rewrite → retrieve → rerank → END` with conditional
  short-circuits (blocked / no-docs / route=direct). Token streaming stays in
  `chat_pipeline.py` (SSE contract FROZEN from E4). If langgraph itself is
  missing/broken, the same node functions run sequentially — degrade, never break.

### 13.4 Embeddings: one 768-dim space per tenant, any provider
All embedding providers (OpenRouter incl. free open-source
`nvidia/llama-nemotron-embed-vl-1b-v2:free` and `qwen/qwen3-embedding-0.6b`,
OpenAI `text-embedding-3-*`, Gemini `gemini-embedding-001`) are requested at
`dimensions=768` (Matryoshka truncation) so the single Qdrant collection keeps
working; a hard dimension check rejects anything else. Because two different
models at 768 dims are still different SPACES, the first successful ingest **pins**
`dc:embedsig:{tenant}` = `provider/model`; mismatched uploads → 409
`embedding_mismatch`; queries always embed with the pinned model; deleting the
last document releases the pin.

### 13.5 Open-source reranker
RRF now over-fetches `RETRIEVAL_POOL` (12) fused candidates; FlashRank
(`ms-marco-TinyBERT`, ~4MB ONNX, CPU — the one deliberate exception to "no local
models") re-scores them against the original question and keeps `RERANK_TOP_K`
(6), renumbering citations. Missing/failed FlashRank degrades to plain RRF order.
