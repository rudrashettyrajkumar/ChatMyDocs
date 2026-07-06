---
name: docchat-conventions
description: DocChat project conventions — config, error degradation, testing, and prompt-file rules. Use when writing or reviewing ANY backend Python code in this repo.
---

# DocChat conventions

## Config discipline
- Every tunable (model IDs, keys, URLs, limits, thresholds, chunk sizes) is read from
  env in `backend/utils/config.py` with a typed default. Agent/service code imports
  `settings` — it never calls `os.getenv` and never contains a model string.
- Adding a config value = three edits: `config.py`, `.env.example` (blank), and the
  ARCHITECTURE §14-equivalent table if user-facing.

## Error degradation (the house style)
Every external call (LLM, embed, Qdrant, Redis) follows this shape:

```python
try:
    result = await asyncio.wait_for(call(), timeout=settings.X_TIMEOUT)
except Exception:
    logger.warning("x_failed", exc_info=True)
    result = SAFE_DEFAULT   # defined next to the call, documented
```

- The user must always receive a valid response/SSE event. No path may raise out of the
  pipeline or hang past its timeout.
- Partial failure → proceed with what succeeded (e.g., one search fails → use the rest).
- Never retry-loop manually around LiteLLM — the Router owns retries/failover.

## Prompts
- All prompt text lives in `backend/prompts/*.md`, loaded once at startup by
  `prompt_assembly.py`. Python may compose blocks (`[CONTEXT]`, `[HISTORY]`,
  `[QUESTION]`) but never contains prose.

## Testing
- `backend/tests/` mirrors module paths. All external services mocked via `conftest.py`
  fixtures — pytest never hits a real API. Live checks belong in `backend/scripts/`
  (eval harness, smoke) and are run deliberately.
- The two invariant tests that must never be deleted or weakened:
  1. guardrail path performs zero LLM router calls,
  2. every Qdrant search call includes the `session_id` filter.
- Prefer golden tests (exact expected output) for chunker and prompt assembly.

## Style
- Python 3.12, full type hints, async-first, `ruff` clean before commit.
- Boring beats clever; a solo fresher developer maintains this.
- Commit format: `feat(E2): pdf ingestion with SSE progress`.
