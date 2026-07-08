"""Batched BYOK embeddings — the canonical gateway, shared by ingestion and retrieval.

Ingestion (E2) and query embedding (E3) must use the SAME model at the SAME
dimensionality. Mixing models between ingest and query puts vectors in
different spaces and silently wrecks retrieval — so per-tenant pinning exists
(`services/embed_signature.py`) and every provider quirk lives HERE, in one
place.

BYOK (v3): `embed()` takes an optional `Selection` (provider/model/key from
the request's `X-Embed-*` headers). All three embedding providers speak
OpenAI's `/embeddings` wire protocol — OpenRouter natively, OpenAI natively,
Gemini via its OpenAI-compatible endpoint — so one httpx code path covers
them. No selection → the server's env default (demo mode, original
behaviour).

Every request pins `dimensions=768` (EMBED_DIM): OpenAI's text-embedding-3,
Gemini's gemini-embedding-001, and Qwen3-Embedding all support Matryoshka
truncation, which is what lets ONE 768-dim Qdrant collection serve every
provider. A provider that ignores the parameter is caught by the hard
dimension check below — a clear error beats silently poisoned vectors.

Gotcha kept from v1: a 200 can still carry an `{"error": ...}` body on
OpenRouter — a paid-credit wall (fail fast) or a transient hiccup.
"""

from __future__ import annotations

import httpx

from backend.llm.runconfig import Selection
from backend.utils.config import get_settings

EMBED_DIM = 768
# OpenAI-compatible bases per embedding provider (not secrets; keys come from
# the request or config).
_BASES: dict[str, str] = {
    "openrouter": "https://openrouter.ai/api/v1",
    "openai": "https://api.openai.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
}
# Sits on the pre-reply hot path for queries and on the ingest path for chunks;
# cap it tight so a slow gateway degrades rather than hangs.
EMBED_TIMEOUT_S = 10.0


class EmbeddingError(RuntimeError):
    """Embedding could not be produced (gateway error, credit wall, bad dims).

    Callers (retrieval_agent, ingest_service) catch this and degrade — e.g. the
    chat path answers without quoted sources rather than hanging.
    """


def server_default_selection() -> Selection:
    """Demo-mode embedding selection from env (litellm-style `EMBED_MODEL` id)."""
    s = get_settings()
    model = s.EMBED_MODEL
    if model.startswith("openrouter/"):
        return Selection(
            provider="openrouter",
            model=model.removeprefix("openrouter/"),
            api_key=s.OPENROUTER_API_KEY or "",
        )
    # A bare id is a config error worth failing loudly on, not routing around.
    raise EmbeddingError(f"EMBED_MODEL must be an openrouter/* id, got {model!r}")


def signature(selection: Selection) -> str:
    """The pinning identity of an embedding space: `provider/model`."""
    return f"{selection.provider}/{selection.model}"


async def _embed_batch(texts: list[str], selection: Selection) -> list[list[float]]:
    """One OpenAI-compatible `/embeddings` call for a single batch, order-preserving."""
    base = _BASES.get(selection.provider)
    if base is None:
        raise EmbeddingError(f"provider {selection.provider!r} cannot serve embeddings")
    try:
        async with httpx.AsyncClient(timeout=EMBED_TIMEOUT_S) as http:
            resp = await http.post(
                f"{base}/embeddings",
                headers={"Authorization": f"Bearer {selection.api_key}"},
                json={
                    "model": selection.model,
                    "input": texts,
                    "dimensions": EMBED_DIM,
                },
            )
            resp.raise_for_status()
            body = resp.json()
    except (httpx.HTTPError, ValueError) as exc:  # network, timeout, 4xx/5xx, bad JSON
        raise EmbeddingError(f"embedding request failed: {exc}") from exc

    rows = body.get("data")
    if not rows:
        # OpenRouter can return 200 with an {"error": ...} body instead of a status code.
        err = body.get("error") or {}
        msg = err.get("message", body) if isinstance(err, dict) else err
        raise EmbeddingError(f"{selection.provider} returned no embedding data: {msg}")
    rows = sorted(rows, key=lambda row: row.get("index", 0))
    vectors = [row["embedding"] for row in rows]
    for vector in vectors:
        if len(vector) != EMBED_DIM:
            raise EmbeddingError(
                f"{signature(selection)} returned {len(vector)}-dim vectors; DocChat "
                f"requires {EMBED_DIM} — pick an embedding model that supports "
                f"{EMBED_DIM} dimensions"
            )
    return vectors


async def embed(texts: list[str], selection: Selection | None = None) -> list[list[float]]:
    """Embed `texts` → 768-dim vectors, batching `EMBED_BATCH_SIZE` per request.

    Order-preserving: returns vectors aligned to `texts`. Raises `EmbeddingError`
    on any failure (empty body, credit wall, wrong dims, network) so the caller
    can degrade.
    """
    if not texts:
        return []
    sel = selection or server_default_selection()
    batch_size = get_settings().EMBED_BATCH_SIZE
    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        vectors.extend(await _embed_batch(batch, sel))
    return vectors
