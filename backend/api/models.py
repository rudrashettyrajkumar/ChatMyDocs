"""`GET /api/models` + `POST /api/models/validate` — the BYOK surface.

GET serves the static catalog (providers, models, accuracy tiers, key-setup
steps) plus this account's runtime facts: whether demo mode is available
(server keys configured) and which embedding space the account is pinned to.

POST /validate makes ONE minimal live call with the submitted key so the UI
can show "key works ✓" before the user commits — a chat ping or a one-string
embedding (which also proves the 768-dim contract). Both routes require auth:
the validator relays arbitrary keys to providers, so it must never be an
anonymous proxy.
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from backend.api.deps import get_tenant_id
from backend.llm import catalog, factory, gateway
from backend.llm.runconfig import BYOKError, RunConfig, Selection, from_headers
from backend.services import embed_signature
from backend.utils import embeddings
from backend.utils.config import get_settings

router = APIRouter()
_log = logging.getLogger("docchat.api.models")

_VALIDATE_TIMEOUT_S = 15.0


@router.get("/api/models")
async def list_models(session_id: str = Depends(get_tenant_id)) -> dict:
    settings = get_settings()
    payload = dict(catalog.catalog_payload())
    payload["demo_available"] = bool(settings.OPENROUTER_API_KEY or settings.GROQ_API_KEY)
    payload["embedding_pin"] = await embed_signature.get_pin(session_id)
    return payload


class ValidateRequest(BaseModel):
    provider: str
    model: str = ""
    api_key: str = Field(min_length=1)
    kind: str = "chat"  # "chat" | "embedding"


def _selection_of(body: ValidateRequest) -> Selection:
    """Reuse runconfig's header validation so /validate and real requests
    accept exactly the same inputs."""
    prefix = "x-embed" if body.kind == "embedding" else "x-llm"
    headers = {
        f"{prefix}-provider": body.provider,
        f"{prefix}-model": body.model,
        f"{prefix}-key": body.api_key,
    }
    cfg: RunConfig = from_headers(headers)
    selection = cfg.embed if body.kind == "embedding" else cfg.chat
    assert selection is not None  # the key header is present, so parsing set it
    return selection


@router.post("/api/models/validate")
async def validate_key(body: ValidateRequest, _: str = Depends(get_tenant_id)) -> dict:
    """One live round-trip with the submitted key → `{ok, detail, latency_ms}`.

    Never raises for provider-side failures: a wrong key is a NORMAL outcome
    here, reported as `ok: false` with the provider's reason attached.
    """
    try:
        selection = _selection_of(body)
    except BYOKError as exc:
        return {"ok": False, "detail": str(exc)}

    started = time.perf_counter()
    try:
        if body.kind == "embedding":
            await embeddings.embed(["ping"], selection)
        else:
            model = factory.build_chat_model(selection, timeout=_VALIDATE_TIMEOUT_S)
            response = await model.ainvoke(
                [{"role": "user", "content": "Reply with the single word: ok"}]
            )
            if not gateway._text_of(response.content).strip():
                return {"ok": False, "detail": "The model returned an empty reply."}
    except Exception as exc:  # noqa: BLE001 — a bad key/model is a result, not a 500
        _log.info(
            "key validation failed",
            extra={"provider": selection.provider, "model": selection.model},
        )
        return {"ok": False, "detail": str(exc)[:300]}

    latency_ms = int((time.perf_counter() - started) * 1000)
    return {
        "ok": True,
        "detail": f"{selection.provider}/{selection.model} responded in {latency_ms} ms.",
        "latency_ms": latency_ms,
    }
