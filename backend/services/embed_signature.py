"""Per-tenant embedding-space pinning (`dc:embedsig:{tenant}`).

A tenant's whole corpus must live in ONE embedding space: query vectors are
only comparable to chunk vectors from the same model. So the FIRST successful
ingest pins `provider/model` for the account; later uploads with a different
`X-Embed-*` selection are rejected up front (409, before any streaming), and
query-time embedding always follows the PIN, not whatever the browser
currently has selected. Deleting the last document releases the pin.

Everything here is best-effort around Redis (errors degrade, never break):
a read failure degrades to "no pin", which at worst embeds a query in the
user's currently-selected space — same failure mode the app had before
pinning existed.
"""

from __future__ import annotations

import logging

from backend.llm.runconfig import RunConfig, Selection
from backend.utils import embeddings
from backend.utils.redis_client import dc_key, get_redis

_log = logging.getLogger("docchat.embed_signature")


def _key(tenant_id: str) -> str:
    return dc_key("embedsig", tenant_id)


def request_selection(cfg: RunConfig) -> Selection:
    """The embedding selection this request ASKS for (BYOK header or demo env)."""
    return cfg.embed or embeddings.server_default_selection()


async def get_pin(tenant_id: str) -> str | None:
    """The tenant's pinned `provider/model` signature, or None (best-effort)."""
    try:
        return await get_redis().get(_key(tenant_id))
    except Exception as exc:  # noqa: BLE001 — a Redis outage must not block embedding
        _log.warning("embed pin read failed; degrading to none", extra={"error": str(exc)})
        return None


async def pin(tenant_id: str, selection: Selection) -> None:
    """Pin the tenant to `selection`'s embedding space (best-effort)."""
    try:
        await get_redis().set(_key(tenant_id), embeddings.signature(selection))
    except Exception as exc:  # noqa: BLE001 — the vectors are already stored; degrade
        _log.warning("embed pin write failed", extra={"error": str(exc)})


async def release_if_empty(tenant_id: str) -> None:
    """Drop the pin once the tenant has no documents left (frees them to
    switch embedding models without support intervention)."""
    redis = get_redis()
    try:
        remaining = await redis.smembers(dc_key("session", tenant_id, "docs"))
        if not remaining:
            await redis.delete(_key(tenant_id))
    except Exception as exc:  # noqa: BLE001 — pin cleanup is never worth a 500
        _log.warning("embed pin release failed", extra={"error": str(exc)})


async def query_selection(tenant_id: str, cfg: RunConfig) -> Selection:
    """The selection to embed QUERIES with: the pin's model, the request's key.

    If the pinned provider matches the request's embed provider, the user's
    key serves the query. Otherwise fall back to the server default when the
    pin is in the server's space; as a last resort use the request selection
    (wrong space, but retrieval already degrades low-relevance rather than
    erroring — same contract as every other retrieval failure).
    """
    requested = request_selection(cfg)
    pinned = await get_pin(tenant_id)
    if pinned is None or pinned == embeddings.signature(requested):
        return requested

    provider, _, model = pinned.partition("/")
    if requested.provider == provider:
        return Selection(provider=provider, model=model, api_key=requested.api_key)

    try:
        server = embeddings.server_default_selection()
        if embeddings.signature(server) == pinned:
            return server
    except embeddings.EmbeddingError:
        pass

    _log.warning(
        "pinned embed space unreachable with this request's keys; using requested space",
        extra={"pinned": pinned, "requested": embeddings.signature(requested)},
    )
    return requested
