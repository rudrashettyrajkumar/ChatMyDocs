# Case Study: DocChat — a RAG chatbot clients can actually trust

## The problem

Ask a non-technical business owner why they're hesitant about an "AI chatbot for our
documents," and you'll hear two fears. The first: *"how do I know it isn't making
things up?"* The second, quieter one: *"do I have to hand over my documents — and my
API bill — to some third party?"* Most demo RAG (retrieval-augmented generation)
projects answer neither. They hallucinate confidently, or dodge every hard question
with a generic "I don't know," and they route everything through the builder's own
account. DocChat is built to answer both fears directly.

Every claim in every answer carries a `[1]`, `[2]`, `[3]`-style citation back to the
exact page it came from, and when a question genuinely isn't covered by the uploaded
documents, the app says so instead of guessing. And through **Bring Your Own Key**, a
user picks any AI provider — a free one, or their own paid account — pastes their key,
and it never leaves their browser. No account required to try it: a keyless demo mode
runs on free open-source models.

## Constraints

The first version was built solo in about a week on a ₹0 incremental budget — no new
paid services, riding entirely on free tiers (Qdrant Cloud, Upstash Redis, an existing
Railway plan) and existing OpenRouter credit. A later iteration added the
bring-your-own-key, multi-provider layer. Both had the same rule: get accuracy, safety,
and flexibility from *architecture*, not from throwing paid infrastructure at the
problem.

## Key decisions, and why

**Keys never touch the server.** The obvious way to support "bring your own key" is to
store each user's key server-side. DocChat deliberately doesn't. A key lives only in
the browser and travels with each request in a header that is parsed, used, and thrown
away — never written to a database, a log, or the cache. It's a small architectural
discipline that turns "trust me with your API key" into "your key never leaves your
machine," which is exactly the reassurance a cautious client needs.

**Adopting a framework once the requirements earned it.** An earlier version ran on
hand-written provider routing with no framework — the right call when there was one
provider and one path. Supporting five providers with per-request key switching, plus a
multi-step pipeline where every step needs a timeout and a fallback, changed the math:
that's precisely the problem LangChain and LangGraph exist to solve, and re-implementing
it by hand would have been the actual liability. Reversing an earlier decision when the
requirements move is judgment, not churn.

**A cheap reranker, and a performance bug caught in the act.** Retrieval fuses several
rewritten queries with Reciprocal Rank Fusion, then a tiny (~4MB) open-source
cross-encoder reranks the top candidates — accuracy for near-zero cost, degrading to
plain fusion if the model can't load. Testing the free demo models live surfaced a
real bug: some "reasoning" models silently burn a hidden thinking budget before the
first visible word, turning a 14-second answer into a 74-second one. Diagnosing and
disabling that (for the one provider where it applied) is the kind of fix you only find
by measuring the real thing, not the mock.

**A payload filter, not per-tenant collections.** Qdrant supports one collection per
tenant for hard isolation, but that doesn't scale on a free cluster with an unknown
number of signups. Instead every chunk is tagged with the owning account, and every
single retrieval query — enforced at one choke point, with a test asserting it —
carries that filter. Same isolation guarantee, no per-tenant infrastructure cost.

## Result

Measured on the v3 build, demo mode (free open-source models — the slowest path):
**~5 seconds** from PDF upload to searchable, and **~5 seconds** median
time-to-first-token, with the answer then streaming to completion. A user who brings a
fast key (Groq's free tier or a paid provider) gets quicker still. The answer streams
token-by-token with heartbeats through Railway's proxy, so even a slow answer never
looks like a hang, and a daily job sweeps any upload that crashed mid-ingestion so
failed uploads never quietly accumulate as orphaned storage.

The result is a small, fully-inspectable RAG system a client can point at their own
documents, on their own key, and trust the citations on — built for close to zero
incremental infrastructure cost.
