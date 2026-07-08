# Case Study: DocChat — a RAG chatbot clients can actually trust

## The problem

Ask a non-technical business owner why they're hesitant about an "AI chatbot for our
documents," and the answer is almost always some version of *"how do I know it isn't
making things up?"* Most demo RAG (retrieval-augmented generation) projects either
hallucinate confidently or dodge every hard question with a generic "I don't know."
Neither builds trust. DocChat was built to answer that specific fear: every claim in
every answer carries a `[1]`, `[2]`, `[3]`-style citation back to the exact page it
came from, and when a question genuinely isn't covered by the uploaded documents, the
app says so instead of guessing.

## Constraints

This was built solo in about a week, on a ₹0 incremental budget — no new paid
services, riding entirely on free tiers (Qdrant Cloud, Upstash Redis, an existing
Railway Hobby plan) and OpenRouter credit already in hand. Those constraints shaped
almost every technical decision below: there was no budget for a dedicated reranking
model, a managed vector database with per-tenant isolation, or a heavyweight
orchestration framework — so the design had to get accuracy and safety from
architecture, not from throwing more paid infrastructure at the problem.

## Key decisions, and why

**No LangChain, no agent framework.** The entire pipeline is plain Python `asyncio`
and FastAPI. For a system this size — parse, chunk, embed, retrieve, answer — a
general-purpose agent framework adds abstraction and debugging overhead without
adding capability. Every step is a function call you can read top to bottom, which
matters more for a demo a client will actually inspect than for a framework logo.

**RRF (Reciprocal Rank Fusion) instead of a reranker.** A dedicated cross-encoder
reranker is the "correct" way to sharpen retrieval quality, but it's another paid
model call on every question. Instead, one question is rewritten into 2–4 standalone
search queries (so a follow-up like "what about page 5?" still retrieves correctly),
and their results are fused with RRF — a well-established, zero-cost-per-query
technique that rewards chunks multiple query variants agree on. It closes most of the
gap a reranker would, for free.

**A payload filter, not per-tenant collections.** Qdrant supports one collection per
tenant for hard isolation, but that doesn't scale on a free-tier cluster with an
unknown number of signups. Instead, every document chunk is tagged with the owning
account's ID, and every single retrieval query — enforced at one choke point in the
code, with a test asserting it — carries that filter. Same isolation guarantee, no
per-tenant infrastructure cost.

## Result

The live deployment (Railway + Cloudflare Pages, both free-tier) measures **~4.2
seconds** from PDF upload to fully searchable, and **~4.2 seconds** time-to-first-token
on a question — both real numbers from the production deployment, not a local dev
box. The answer streams token-by-token with heartbeats through Railway's proxy, so
even a slower answer never looks like a hang. A daily cleanup job sweeps any upload
that crashed mid-ingestion before it could be recorded against an account, so failed
uploads never quietly accumulate as orphaned storage.

The result is a small, fully-inspectable RAG system that a client can point at their
own documents and trust the citations on — built for close to zero incremental
infrastructure cost.
