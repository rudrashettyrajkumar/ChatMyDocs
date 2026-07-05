"""Batched embedding — the canonical gateway, shared by ingestion and retrieval.

Ingestion (E2) and query embedding (E3) must use the SAME `gemini-embedding-001`
model at 768 dims, served VIA OpenRouter. Mixing models or gateways between
ingest and query would put the two vectors in different spaces and silently
wreck retrieval — so the gateway quirks live here, in ONE place.

OpenRouter gotcha: POST OpenRouter's OpenAI-compatible `/embeddings` with raw
httpx, sending `dimensions=768`. litellm rejects `dimensions` for
`openrouter/*` (would silently return a different dimensionality) and the
openai SDK defaults to base64 encoding. A 200 can still carry an `{"error":
...}` body — a paid-credit wall (fail fast) or a transient hiccup.

Batched at `EMBED_BATCH_SIZE` (config, default 100) per request — a 100-page
PDF's ~150 chunks costs 2 requests (ARCHITECTURE §3.1).
"""

from __future__ import annotations

import httpx

from backend.utils.config import get_settings

EMBED_DIM = 768
# OpenRouter's OpenAI-compatible base (not a secret; the key comes from config).
_OPENROUTER_BASE = "https://openrouter.ai/api/v1"
# Sits on the pre-reply hot path for queries and on the ingest path for chunks;
# cap it tight so a slow gateway degrades rather than hangs.
EMBED_TIMEOUT_S = 10.0


class EmbeddingError(RuntimeError):
    """Embedding could not be produced (gateway error or credit wall).

    Callers (retrieval_agent, ingest_service) catch this and degrade — e.g. the
    chat path answers without quoted sources rather than hanging.
    """


async def _embed_batch(texts: list[str], model: str, api_key: str | None) -> list[list[float]]:
    """One OpenRouter `/embeddings` call for a single batch, order-preserving."""
    try:
        async with httpx.AsyncClient(timeout=EMBED_TIMEOUT_S) as http:
            resp = await http.post(
                f"{_OPENROUTER_BASE}/embeddings",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model.removeprefix("openrouter/"),
                    "input": texts,
                    "dimensions": EMBED_DIM,
                },
            )
            resp.raise_for_status()
            body = resp.json()
    except (httpx.HTTPError, ValueError) as exc:  # network, timeout, bad JSON
        raise EmbeddingError(f"embedding request failed: {exc}") from exc

    rows = body.get("data")
    if not rows:
        # OpenRouter returns 200 with an {"error": ...} body instead of a status code.
        err = body.get("error") or {}
        msg = err.get("message", body) if isinstance(err, dict) else err
        raise EmbeddingError(f"openrouter returned no embedding data: {msg}")
    rows = sorted(rows, key=lambda row: row.get("index", 0))
    return [row["embedding"] for row in rows]


async def embed(texts: list[str]) -> list[list[float]]:
    """Embed `texts` → 768d vectors, batching `EMBED_BATCH_SIZE` per request.

    Order-preserving: returns vectors aligned to `texts`. Raises `EmbeddingError`
    on any failure (empty body, credit wall, network) so the caller can degrade.
    """
    if not texts:
        return []
    settings = get_settings()
    model = settings.EMBED_MODEL
    if not model.startswith("openrouter/"):
        # DocChat is OpenRouter-only for embeddings; a stray bare id is a config
        # error, not something to silently route around.
        raise EmbeddingError(f"EMBED_MODEL must be an openrouter/* id, got {model!r}")

    batch_size = settings.EMBED_BATCH_SIZE
    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        vectors.extend(await _embed_batch(batch, model, settings.OPENROUTER_API_KEY))
    return vectors
