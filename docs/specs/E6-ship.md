# SPEC E6 — Ship: deploy, cleanup cron, README, Loom, case study

**Epic:** E6 · **Depends on:** E5 · **Architecture refs:** §9, §12

## Objective
DocChat is live on the internet, self-cleaning, monitored, and packaged as a portfolio
asset: README with demo link + GIF, a 2-minute Loom script, and a short case-study
writeup ready for Upwork/LinkedIn.

## Deliverables
```
.github/workflows/cleanup.yml        # daily: cleanup_expired.py + Qdrant keepalive
backend/scripts/cleanup_expired.py   # delete Qdrant points created_at < now-24h
README.md                            # the portfolio artifact
docs/CASE-STUDY.md                   # 400–600 word writeup
docs/LOOM-SCRIPT.md                  # 2-min shot-by-shot script
Live deployments: Railway (backend) + Cloudflare Pages (frontend)
UptimeRobot monitor on /health
```

## Requirements
1. **Deploy backend** to Railway as a second service in the existing project (shared
   Hobby credit): Dockerfile build, all env vars set, spend alert already configured.
   Verify SSE works through Railway's proxy (long-lived responses + heartbeat).
2. **Deploy frontend** to Cloudflare Pages: `VITE_API_URL` → Railway URL; CORS on the
   backend locked to the Pages domain (+ localhost for dev).
3. **Cleanup cron** (GitHub Actions daily): `cleanup_expired.py` deletes expired points
   via `created_at` range filter, logs deleted count; the same workflow's Qdrant API hit
   doubles as the free-tier keepalive. Redis needs nothing (native TTL).
4. **Smoke script** `scripts/smoke.sh`: health → upload sample → ask question → assert
   citation in output. Run against prod after every deploy.
5. **README** (this is what clients actually read): one-line pitch → live demo link →
   30s GIF of upload→cited answer → architecture diagram (ASCII from §2 is fine) →
   "Engineering highlights" (5 bullets: RRF multi-query, SSE hardening, provider
   failover, injection guardrail, session isolation + TTL cleanup) → local setup →
   honest "Limitations & next steps" (no OCR, single language, no reranker).
6. **CASE-STUDY.md**: problem → constraints (free-tier, 1 week) → key decisions and WHY
   (no LangChain, RRF over reranker, payload filter over per-tenant collections) →
   result (latency numbers from real measurements). Written for a non-technical client
   skimming an Upwork profile.
7. **LOOM-SCRIPT.md**: 0:00 hook ("watch it cite page 14"), 0:15 upload, 0:40 question +
   streaming, 1:10 citation click, 1:25 "docs don't cover this" refusal demo, 1:40
   architecture flash + CTA. Raj records this himself — script keeps it under 2:00.

## Acceptance criteria
- Fresh phone on mobile data completes the full happy path on the live URL.
- `smoke.sh` passes against production.
- Cleanup workflow ran once (manual dispatch) and deleted seeded expired points.
- UptimeRobot green; README GIF plays on GitHub; case study reviewed by Raj.
- Measured and recorded in README: time-to-first-token and ingest time for sample.pdf.

## Required tests
- cleanup_expired: mocked Qdrant — correct filter (created_at range only, no session
  filter), dry-run flag works.
- No new pytest surface otherwise — this epic's verification is the smoke script + the
  acceptance checklist above.
