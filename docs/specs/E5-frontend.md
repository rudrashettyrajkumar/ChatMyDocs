# SPEC E5 — Frontend: upload UX, streaming chat, citations panel

**Epic:** E5 · **Depends on:** E4 (live API) · **Architecture refs:** §7, §8

## Objective
The single-screen React app per §8: sidebar (dropzone + doc cards + ingest progress) and
chat (streamed markdown answers, citation chips, sources drawer). Polished enough to BE
the portfolio — this screen appears in the Loom video and Upwork profile.

## Deliverables
```
frontend/  (Vite + React 18 + Tailwind; no heavy UI kit)
├── src/lib/session.ts          # UUID v4 in localStorage, X-Session-Id on every call
├── src/api/client.ts           # typed fetch wrapper + SSE reader (fetch streams, not EventSource —
│                               #   POST bodies needed; parse event/data frames manually)
├── src/hooks/useUpload.ts      # multipart POST, consumes progress SSE
├── src/hooks/useChatStream.ts  # token assembly by seq, sources event, reconnect/backoff
├── src/components/
│   ├── Sidebar.tsx  Dropzone.tsx  DocCard.tsx  IngestProgress.tsx
│   ├── Chat.tsx  MessageList.tsx  Composer.tsx
│   ├── CitationChip.tsx  SourcesDrawer.tsx
│   └── EmptyState.tsx  ErrorBanner.tsx
└── src/App.tsx
```

## Task breakdown (build in this order)
1. **Shell & session**: layout grid, session bootstrap, API client, health check on load
   (backend asleep/unreachable → friendly banner, not white screen).
2. **Upload flow**: dropzone (drag + click), client-side pre-checks (type/size) for
   instant feedback, progress bar driven by the SSE stages from E2, doc cards with
   name/pages/chunks/delete, all four server rejection errors rendered as human messages.
   "Try a sample PDF" button → calls a dedicated endpoint or uploads the bundled sample.
3. **Chat flow**: composer disabled until ≥1 doc ready (tooltip explains why); user
   message renders immediately; assistant tokens append live (respect seq — drop
   duplicates after reconnect); markdown rendering (react-markdown, no raw HTML);
   3 suggested starter questions shown when chat is empty (generic, e.g. "Summarize
   this document").
4. **Citations**: `[n]` in answer text becomes a CitationChip (regex post-process on the
   final text; during streaming plain `[n]` is fine). Chip click → SourcesDrawer opens
   scrolled to source n: filename, page, snippet, cited/uncited (uncited dimmed).
   Citation numbers with no matching source are stripped (safety net per §5.4).
5. **Resilience & states**: SSE drop → retry 1s/2s/4s/8s with "reconnecting…" state,
   then a retry button — never a raw error or a forever-spinner. 429 → friendly limit
   message. Empty states designed. "Documents auto-delete after 24h" note in sidebar.
6. **Polish**: mobile-usable (sidebar collapses to a sheet), dark theme default, favicon,
   `<title>`, OG tags (link previews matter when Raj shares this on LinkedIn),
   footer: "Built by Raj — FastAPI · Qdrant · RRF · SSE" linking to GitHub.

## Acceptance criteria
- Full happy path in a fresh incognito window: sample PDF → question → streamed cited
  answer → chip → correct source, in under 30s of user effort.
- Kill the network mid-answer (devtools offline) → reconnecting state → graceful recovery
  or clean retry prompt.
- Lighthouse: no console errors; usable at 375px width.
- `VITE_API_URL` is the only env; `npm run build` output deploys to Cloudflare Pages as-is.

## Required tests
- Unit-test the two hooks (mock SSE frames): token assembly ordering, sources parsing,
  reconnect dedup by seq. Component tests optional — visual QA via the acceptance
  checklist is the bar for a 1-week demo.
