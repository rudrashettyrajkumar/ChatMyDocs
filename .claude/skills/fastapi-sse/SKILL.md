---
name: fastapi-sse
description: SSE streaming patterns — event framing, heartbeats, sequence IDs, guard_stream output rail, and the frontend fetch-stream client. Use when working on /chat/stream, /documents progress, or the React streaming hooks.
---

# SSE patterns (DocChat)

## Server side (FastAPI)

- `StreamingResponse(gen(), media_type="text/event-stream")` with headers
  `Cache-Control: no-cache`, `X-Accel-Buffering: no`.
- Event framing helpers live in `backend/utils/sse.py` (ported from MyShiva) — use them,
  don't hand-format `data:` lines at call sites.

### The event contract (frozen — frontend binds to it)

Chat stream:
```
data: {"token": "...", "seq": 0}          # repeated
: ping                                    # heartbeat comment every 15s of silence
data: {"event": "sources", "sources": [{"n":1,"doc_id":"…","filename":"…",
       "pages":"14","snippet":"…","score":0.71,"cited":true}, …]}
data: {"event": "done"}
```
Ingest progress: `{"stage": "parsing"|"chunking"|"embedding"|"ready"|"error", …}`.
Errors are ALWAYS a valid event `{"event":"error","detail":"friendly text"}` — never a
dropped connection or raw traceback.

### Rules
- `seq` is monotonically increasing per response; the client dedups on reconnect with it.
- Heartbeat: emit `: ping\n\n` if no token for 15s (asyncio.wait_for pattern around the
  token iterator) — Railway's proxy and browsers both need proof of life.
- Wrap the model token stream in `guardrails.guard_stream()` — it cuts the stream before
  a leaked internal marker (`[CONTEXT]`, `[HISTORY]`, `[QUESTION]`) reaches the client
  and substitutes the error event.
- BackgroundTasks for post-stream work (history append, counters) — never await it inside
  the generator after `done`.

## Client side (React)

- POST bodies rule out `EventSource`. Use `fetch` + `ReadableStream` reader; split frames
  on `\n\n`, ignore comment lines (`: ping`), `JSON.parse` each `data:` payload.
- Assemble tokens in seq order; after a reconnect, drop frames with seq ≤ last seen.
- Reconnect policy: exponential 1s/2s/4s/8s with a visible "reconnecting…" state, then a
  manual retry button. Never a raw error string, never an infinite spinner.
- Distinguish terminal states: `done` (finalize message, render citation chips),
  `error` (show friendly banner, keep partial text), network drop (reconnect flow).
