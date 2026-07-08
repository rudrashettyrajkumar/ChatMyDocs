# DocChat — Project Memory

Portfolio Project #1: "Chat with your documents" — PDF upload → Qdrant → streamed,
page-cited answers. A generalized, demo-grade version of the MyShiva RAG pipeline.
Goal: live demo + Loom video that wins freelance clients. Built in ~1 week.

## Source of truth (read before implementing anything)
- `docs/ARCHITECTURE.md` — final design. NEVER contradict it; if a task seems to require
  deviating, STOP and ask the developer first.
- `docs/specs/` — one spec per epic. Implement exactly one epic per session.
- `docs/BUILD-PROMPTS.md` — the session prompt for each epic.
- MyShiva reference code (patterns to port, not import):
  `/mnt/d/PortfolioProjects/MyShiva/backend/`

## Hard constraints
- ₹0 incremental cost: existing Railway Hobby, Qdrant free cluster, Upstash free,
  OpenRouter credit. Never add a paid service without flagging it. BYOK usage bills
  the USER's key, never ours.
- **Demo mode serves ONLY free-tier open-source models** (NVIDIA Nemotron `:free`
  via OpenRouter for chat + embeddings, open-source Llama on Groq as failover) —
  never a paid or proprietary model. When it fails, the user-facing error says
  it's the free tier and points at bringing their own key.
- **LangChain + LangGraph ARE the LLM layer (v3, 2026-07-08, Raj-requested — this
  REVERSES the original "no frameworks" lock).** LiteLLM is gone. The graph lives in
  `backend/graph/chat_graph.py`; provider construction only in `backend/llm/factory.py`;
  agents call `backend/llm/gateway.py`, never a provider SDK.
- Container stays stateless and near-featherweight: no torch, no files on disk; PDFs
  parsed in memory. One deliberate exception: FlashRank's ~4MB ONNX reranker
  (degrades to no-op if absent).
- **BYOK keys are never stored server-side.** They live in the browser (localStorage)
  and arrive per-request via `X-LLM-*` / `X-Embed-*` headers, parsed ONLY in
  `backend/llm/runconfig.py`. Never log a key; never write one to Redis.

## Stack (v3)
FastAPI on Railway · Qdrant Cloud (collection `docchat_chunks`, 768-dim cosine — ALL
embedding providers pinned to 768 via Matryoshka `dimensions`) · Upstash Redis (`dc:`
prefix) · LangChain (ChatOpenAI for OpenRouter/Groq/OpenAI + ChatAnthropic +
ChatGoogleGenerativeAI) + LangGraph workflow · FlashRank reranker · PyMuPDF ·
React 18 + Vite + Tailwind + react-router + motion on Cloudflare Pages.
BYOK providers: Groq (free) · OpenRouter (free tier) · OpenAI · Anthropic · Gemini;
demo mode (no key) = env-configured OpenRouter→Groq chain, original quotas.

## Auth & tenancy (added post-E-design, overrides original "no auth")
Self-contained **email/password auth**, no external provider: users live in Upstash
(`dc:user:{email}` + `dc:userid:{id}`, bcrypt-free PBKDF2 hashing via stdlib), and we
mint our OWN HS256 JWT (`JWT_SECRET`, 7-day). Login is required for everything. The
authenticated **user id is the tenant key** — it is what threads through the code as
`session_id` and scopes every Qdrant search + `dc:*` key. Documents and chat history
**persist with the account** (no TTL); only the per-day rate-limit counters expire.
Frontend: `/` landing, `/login`, `/register`, protected `/app`; JWT in localStorage,
sent as `Authorization: Bearer`; a 401 logs the user out. Light-first colorful
glassmorphism UI with a dark-mode toggle (see `docs/DESIGN-SYSTEM.md`).

## Non-negotiable invariants
1. **Input guardrail runs before any LLM call**; blocked messages never reach a model
   and are never stored in history. Tests assert zero router calls on that path.
2. **Every Qdrant search carries the tenant (`session_id`) filter**, applied at one choke
   point in retrieval_agent. The tenant value is now the authenticated user id; the
   payload field name stays `session_id`. A test asserts cross-tenant isolation.
3. All model IDs, keys, and limits from env via `backend/utils/config.py` — never
   hardcoded — EXCEPT the BYOK catalog (`backend/llm/catalog.py`), which is the one
   deliberate registry of user-selectable models, and per-request BYOK headers.
   3b. A tenant's corpus lives in ONE embedding space: first ingest pins
   `dc:embedsig:{tenant}`; mismatched uploads 409; queries embed with the PINNED
   model (`services/embed_signature.py`). Deleting the last doc releases the pin.
4. Grounded answers only: cite [n] per claim; on low relevance say the documents don't
   cover it. Never invent document content.
5. Errors degrade, never break: timeout + fallback on every external call; the user
   always gets a valid SSE event, never a hang or raw traceback.
6. Prompt text lives in `backend/prompts/*.md`, never in Python strings.

## Code conventions
- Python 3.12, full type hints, async-first. `ruff` clean before any commit.
- Tests in `backend/tests/` mirroring module paths; external services mocked via
  `tests/conftest.py` fixtures — tests never hit real APIs (except the eval harness and
  smoke script, which are explicitly live and live in `scripts/`).
- Secrets: `.env` (gitignored) + `.env.example` (committed, blank values).

## Workflow
- One epic per session. After implementing: run pytest + ruff, then `/spec-check
  <spec path>` before declaring done.
- Commit format: `feat(E3): retrieval agent with RRF and session isolation`.
- If a spec is ambiguous: smallest reasonable choice, note it in the commit body, flag it.
