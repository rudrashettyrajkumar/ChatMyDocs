# Loom Script — DocChat (under 2:00)

Record at https://docchat-98q.pages.dev. Have `sample/sample.pdf` ready on your
desktop. Sign in with a fresh demo account before hitting record so the whole take is
signal, no dead time on the login form. Do one dry run first and note which page a real
citation lands on — use that exact page number in the hook.

---

**0:00 — Hook**
> "Watch it answer a question and cite the exact page it got the answer from."

Cold open on the empty chat screen. Don't explain the stack yet — just say the line
and move.

**0:12 — Upload**
Drag `sample.pdf` onto the dropzone. Let the real ingest progress bar play out
(parsing → chunking → embedding → ready) — don't cut it, the progress bar *is* the
proof it's not faked.

**0:35 — Question + streaming**
Type: *"What is this document about? Cite your sources."* Let the answer stream
token-by-token on screen — don't skip ahead. Narrate over it, low-key:
> "It rewrites the question, searches the document, reranks the best passages, and
> streams the answer — every claim tagged with a citation."

**1:05 — Citation click**
Click one of the `[n]` citation markers in the answer. The source drawer opens showing
the exact passage and page number it came from.
> "Every claim traces back to a real page — click it, see it."

**1:20 — Refusal demo**
Ask something the document plausibly *could* cover but doesn't, e.g. *"What is the
narrator's husband's annual salary?"* Show the model declining instead of guessing:
> "And when the documents don't actually cover something, it says so — it doesn't
> invent a number."

**1:35 — Bring Your Own Key flash**
Open the Model Studio (the model chip at the top). Show the provider cards for a beat.
> "It's running on a free demo model right now — but you can bring your own key, any
> provider, and it never leaves your browser."

**1:50 — Architecture flash + CTA**
Cut to the architecture diagram (`README.md`) for 2–3 seconds while you say:
> "FastAPI, LangGraph, Qdrant — retrieval, reranking, streamed and cited. If you need
> this for your own documents, message me — link's below."

End on the live URL on screen.

---

## Recording notes

- Resolution: 1280×800 browser window (matches the README GIF crop).
- Keep total runtime under 2:00 — trim dead air in editing, not by rushing the talk.
- Demo mode runs on free open-source models, so first-token is ~5s and can occasionally
  spike — do a dry run and, if a take hits a slow free-tier moment, just re-record;
  don't speed up the footage (it reads as faked).
- Optional flex: before recording, paste a Groq free key in the Model Studio so the
  answer streams noticeably faster on camera — then mention "on your own key it's
  quicker" during the BYOK beat.

## Recording the README GIF (`docs/demo.gif`)

The GIF is a ~15–25s silent loop of **upload → streamed answer → citation click** (no
BYOK/refusal beats — keep it short so it plays inline on GitHub).

1. **Capture the screen region** to a short `.mp4`. Use whatever records cleanly on
   your machine — on Windows, [ScreenToGif](https://www.screentogif.com/) or the Xbox
   Game Bar (`Win+G`); on a Linux desktop, `peek` or
   `ffmpeg -f x11grab -framerate 20 -video_size 1280x800 -i :0.0+0,0 demo-raw.mp4`.
   Crop tight to the app, ~1280×800.
2. **Convert to a small, crisp GIF** with ffmpeg's two-pass palette method (keeps it
   well under GitHub's inline limit):
   ```bash
   # from the repo root, with your recording as demo-raw.mp4
   ffmpeg -i demo-raw.mp4 -vf "fps=12,scale=960:-1:flags=lanczos,palettegen" -y palette.png
   ffmpeg -i demo-raw.mp4 -i palette.png \
     -lavfi "fps=12,scale=960:-1:flags=lanczos[x];[x][1:v]paletteuse" \
     -y docs/demo.gif
   rm palette.png demo-raw.mp4
   ```
3. Confirm `docs/demo.gif` is under ~8 MB (`ls -lh docs/demo.gif`); if larger, drop
   `fps=12` to `fps=10` or `scale=960` to `scale=800` and re-run the second command.
4. Commit it: `git add docs/demo.gif && git commit -m "docs: add demo GIF"`. It renders
   in the README automatically (the image link is already there).
