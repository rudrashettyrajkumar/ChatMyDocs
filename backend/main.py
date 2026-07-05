"""FastAPI app factory. Entrypoint: `uvicorn backend.main:app`."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api import documents, health
from backend.scripts.create_collection import ensure_collection
from backend.utils import redis_client
from backend.utils.config import get_settings

logging.basicConfig(level=logging.INFO)
_log = logging.getLogger("docchat.app")


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    # Pay the Upstash TLS handshake before the first user request (measured
    # >2s cold — it would otherwise blow the per-call timeout on that request).
    # Best-effort: a failure here must never block boot (errors degrade).
    try:
        await redis_client.warm_up()
    except Exception as exc:  # noqa: BLE001 — warm-up is an optimization, not a gate
        _log.warning("redis warm-up failed; will warm on first use", extra={"reason": repr(exc)})
    # Idempotent collection/index setup (spec E2 Req 5: "called on startup
    # too"). Best-effort for the same reason — a half-configured dev box must
    # still boot.
    try:
        await ensure_collection()
    except Exception as exc:  # noqa: BLE001 — collection setup is not a boot gate
        _log.warning("qdrant collection setup failed", extra={"reason": repr(exc)})
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="DocChat", version="0.1.0", lifespan=_lifespan)

    # CORS: the SSE client lives on a different origin (Cloudflare Pages).
    # Keep FRONTEND_ORIGIN a concrete origin — never "*" alongside credentials.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.FRONTEND_ORIGIN],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(documents.router)

    return app


app = create_app()
