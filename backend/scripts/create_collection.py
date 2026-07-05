"""Idempotent Qdrant collection + payload-index setup (spec E2 Req 5,
ARCHITECTURE §5.1).

Run standalone (`python -m backend.scripts.create_collection`) or awaited from
`main.py`'s startup lifespan (spec Req 5: "called on startup too") — either
way it's a no-op once the collection and its indexes already exist.
"""

from __future__ import annotations

import asyncio
import logging

from backend.utils.config import get_settings
from backend.utils.embeddings import EMBED_DIM
from backend.utils.qdrant_client import get_qdrant

_log = logging.getLogger("docchat.create_collection")

# ARCHITECTURE §5.1: session_id/doc_id are exact-match filters (tenant
# isolation, per-doc delete); created_at is a numeric range filter (24h
# cleanup cron).
_INDEXED_FIELDS = ("session_id", "doc_id", "created_at")


async def ensure_collection() -> None:
    from qdrant_client import models

    client = get_qdrant()
    settings = get_settings()
    name = settings.QDRANT_COLLECTION

    if not await client.collection_exists(name):
        await client.create_collection(
            collection_name=name,
            vectors_config=models.VectorParams(size=EMBED_DIM, distance=models.Distance.COSINE),
        )
        _log.info("created collection", extra={"collection": name})

    for field in _INDEXED_FIELDS:
        is_numeric = field == "created_at"
        schema = models.PayloadSchemaType.FLOAT if is_numeric else models.PayloadSchemaType.KEYWORD
        try:
            await client.create_payload_index(
                collection_name=name, field_name=field, field_schema=schema
            )
        except Exception as exc:  # noqa: BLE001 — "index already exists" is the common case
            _log.debug(
                "payload index already present", extra={"field": field, "error": str(exc)}
            )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(ensure_collection())
