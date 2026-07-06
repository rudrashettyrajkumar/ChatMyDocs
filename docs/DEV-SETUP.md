# DocChat — Local Dev Setup

Working notes for running the app locally during development. The polished,
client-facing `README.md` (demo link, GIF, architecture diagram, case study) is an
**E6 deliverable** — it doesn't exist yet because it needs a live deploy first
(see `docs/specs/E6-ship.md`). This file is just "how do I run it right now."

## Prerequisites
- Python 3.12 (backend venv already at `.venv/`)
- Node 18+ and npm (frontend)
- A `.env` in the repo root with real credentials — see `.env.example` for the list.
  Required to actually boot the stateful endpoints: `OPENROUTER_API_KEY`,
  `GROQ_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`, `UPSTASH_URL`, `UPSTASH_TOKEN`.
  (DocChat reuses the same OpenRouter/Groq/Qdrant/Upstash accounts as MyShiva —
  just a new Qdrant collection and a `dc:` Redis key prefix, no new accounts needed.)

## Backend

```bash
cd /mnt/d/PortfolioProjects/DocChat
.venv/bin/uvicorn backend.main:app --reload --port 8000
```

First boot creates the `docchat_chunks` Qdrant collection + indexes automatically
(`backend/scripts/create_collection.py`, called from `main.py` on startup) — this is a
one-time, idempotent setup against your real cluster, takes a few seconds.

Verify it's up: `curl http://localhost:8000/health` → expect
`{"status":"ok","qdrant":"ok","redis":"ok","llm":"ok"}`. If any dep shows `"down"`,
double check that value in `.env`.

## Frontend

```bash
cd /mnt/d/PortfolioProjects/DocChat/frontend
npm install   # first time only
npm run dev
```

Opens on `http://localhost:5173`. Reads `VITE_API_URL` from `frontend/.env`
(defaults to `http://localhost:8000`) — only change it if the backend runs elsewhere.

**Start the backend first.** The frontend shows a "can't reach the backend" banner
until `/health` responds.

## Tests & checks (backend)

```bash
cd /mnt/d/PortfolioProjects/DocChat
.venv/bin/pytest
.venv/bin/ruff check .
```

## Tests & checks (frontend)

```bash
cd /mnt/d/PortfolioProjects/DocChat/frontend
npx tsc -b        # typecheck
npm run lint      # eslint
```
