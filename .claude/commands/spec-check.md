---
description: Verify the current implementation against an epic spec before declaring it done. Usage: /spec-check docs/specs/E2-ingestion.md
---

Verify the implementation against the spec at: $ARGUMENTS

Do this strictly:

1. Read the spec fully. Build a checklist from three sections: **Deliverables** (every
   file), **Requirements** (every numbered item), **Required tests** (every test).
2. For each deliverable file: confirm it exists and actually implements what the spec
   says (read it — existence alone is not a pass).
3. For each requirement: find the code that satisfies it and cite `file:line`. If a
   requirement is only partially met, say exactly what's missing.
4. For each required test: confirm the test exists AND meaningfully asserts the behavior
   (a test that mocks away the thing it claims to test is a FAIL). Then run
   `python -m pytest backend/tests/ -q` and `ruff check backend/`.
5. Cross-check against CLAUDE.md invariants — especially: zero LLM calls on the guardrail
   path, session_id filter on every Qdrant search, no hardcoded model strings, no prompt
   prose in Python, no secrets.

Output a verdict table: ✅ met / ⚠️ partial / ❌ missing per item, with file:line
references, followed by PASS or FAIL overall. FAIL if any requirement or required test
is ❌, or pytest/ruff fail. Do not fix anything in this pass — report only.
