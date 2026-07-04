# SPEC INDEX — DocChat

Implement in this order (dependencies flow downward). **One epic per Claude Code session.**
Paste the matching prompt from `docs/BUILD-PROMPTS.md` to start each session.

| ID | Spec | Side | Depends on | Skills that should trigger |
|---|---|---|---|---|
| E1 | foundation | Backend | — | docchat-conventions |
| E2 | ingestion | Backend | E1 | docchat-conventions, qdrant-rag |
| E3 | retrieval | Backend | E2 | qdrant-rag |
| E4 | chat-pipeline | Backend | E3 | fastapi-sse, docchat-conventions |
| E5 | frontend | UI | E4 (needs live API contract) | fastapi-sse (client section) |
| E6 | ship | DevOps/Polish | E5 | docchat-conventions |

Every spec ends with **Acceptance criteria** and **Required tests**. An epic is DONE only
when: tests pass, `ruff` is clean, and `/spec-check <spec path>` passes.

Commit format: `feat(E2): pdf ingestion with SSE progress` — epic prefix always.
