"""Shared FastAPI dependencies — the one place the tenant boundary is defined.

DocChat authenticates every data route with a bearer JWT (self-contained
email/password auth, see `middleware/jwt_auth.py`). The authenticated account id
is the multi-tenant key: it is what scopes Qdrant searches, the `dc:session:*`
document sets, chat history, and per-account rate limits. Routes depend on
`get_tenant_id` so a missing/invalid token fails with a clean 401 before any
handler logic runs — and so the tenancy source lives in exactly one import.
"""

from __future__ import annotations

from backend.middleware.jwt_auth import get_current_user_id as get_tenant_id

__all__ = ["get_tenant_id"]
