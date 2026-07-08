# Loom Script — DocChat (under 2:00)

Record at https://docchat-98q.pages.dev. Have `sample/sample.pdf` ready on your
desktop. Sign in with a fresh demo account before hitting record so the whole take
is signal, no dead time on the login form.

---

**0:00 — Hook**
> "Watch it cite page 14."

Cold open on the empty chat screen. Don't explain the stack yet — just say the line
and move.

**0:15 — Upload**
Drag `sample.pdf` onto the dropzone. Let the real ingest progress bar play out
(parsing → chunking → embedding → ready) — don't cut it, the progress bar *is* the
proof it's not faked.

**0:40 — Question + streaming**
Type: *"What is this document about? Cite your sources."* Let the answer stream
token-by-token on screen — don't skip ahead. Narrate over it, low-key:
> "No LangChain, no agent framework — this is a plain FastAPI pipeline streaming
> straight from the model."

**1:10 — Citation click**
Click one of the `[n]` citation markers in the answer. The source drawer opens
showing the exact passage and page number it came from.
> "Every claim traces back to a real page — click it, see it."

**1:25 — Refusal demo**
Ask something the document doesn't cover, e.g. *"What's the capital of France?"*
Show the model declining instead of guessing:
> "And when the documents don't cover something, it says so — it doesn't guess."

**1:40 — Architecture flash + CTA**
Cut to the architecture diagram (`README.md` ASCII diagram, or a screenshot of it) for
2–3 seconds while you say:
> "FastAPI, Qdrant, RRF retrieval, streamed and cited. If you need this for your own
> documents, message me — link's below."

End on the live URL on screen.

---

## Recording notes

- Resolution: 1280×800 browser window (matches the README GIF crop).
- Keep total runtime under 2:00 — trim dead air in editing, not by rushing the talk.
- One take is fine; DocChat's real latency (~4s to first token) is fast enough that
  you don't need to speed up the footage.
