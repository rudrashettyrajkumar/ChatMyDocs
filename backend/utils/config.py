"""Single source of truth for all configuration.

CLAUDE.md invariant #3: every model ID, key, and limit reaches the code from an
environment variable *through this module* — never `os.getenv` elsewhere, never
a hardcoded model string in agent code. Values mirror ARCHITECTURE.md §4/§7/§9.
"""

import logging
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_log = logging.getLogger("docchat.config")

# Keys that MUST be present before prod traffic. The LLM gateways, the two data
# stores, and the JWT signing secret are all load-bearing: a prod box that can
# neither reach a model, persist a vector, nor sign an auth token is broken.
REQUIRED_IN_PROD: tuple[str, ...] = (
    "OPENROUTER_API_KEY",
    "GROQ_API_KEY",
    "QDRANT_URL",
    "QDRANT_API_KEY",
    "UPSTASH_URL",
    "UPSTASH_TOKEN",
    "JWT_SECRET",
)


class Settings(BaseSettings):
    """Typed, env-backed settings. Reads `.env` if present (dev only)."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Runtime ---------------------------------------------------------
    ENV: str = "dev"
    FRONTEND_ORIGIN: str = "http://localhost:5173"

    # --- Models (migrate by changing env alone; never touch agent code) --
    # Demo mode runs EXCLUSIVELY on free-tier OPEN-SOURCE models so it never
    # burns paid credit. CHAT runs on Groq's open-source Llama 3.3 70B: it's
    # LPU-fast, cites reliably (verified 6/6), and Groq's free tier is ~1000
    # req/day/model vs OpenRouter's 200/day — so chat gets the roomier budget
    # and OpenRouter's scarce free tier is spent only on EMBEDDINGS (its unique
    # capability here; Groq has no embedding model). The diverse fallback for
    # each chat role is OpenRouter's NVIDIA Nemotron (see factory.demo_chain).
    # Embeddings: NVIDIA `:free` on OpenRouter, 768-dim Matryoshka. `:free`
    # lineups rotate — re-verify at openrouter.ai/collections/free-models.
    REWRITER_MODEL: str = "groq/llama-3.3-70b-versatile"
    ANSWERER_MODEL: str = "groq/llama-3.3-70b-versatile"
    EMBED_MODEL: str = "openrouter/nvidia/llama-nemotron-embed-vl-1b-v2:free"

    # --- Provider credentials -------------------------------------------
    OPENROUTER_API_KEY: str | None = None  # primary gateway (all LLM + embeddings)
    GROQ_API_KEY: str | None = None  # failover provider

    # --- Auth (self-contained email/password → our own HS256 JWT) --------
    # JWT_SECRET signs every session token; keep it long + random in prod.
    # Users persist in Upstash (no TTL) so accounts outlive the 24h data window.
    JWT_SECRET: str | None = None
    JWT_TTL_DAYS: int = 7

    # --- Data stores -------------------------------------------------------
    QDRANT_URL: str | None = None
    QDRANT_API_KEY: str | None = None
    QDRANT_COLLECTION: str = "docchat_chunks"
    UPSTASH_URL: str | None = None
    UPSTASH_TOKEN: str | None = None

    # --- Tunables (ARCHITECTURE §7/§9, spec E1 Req 1) ---------------------
    MAX_CONCURRENT_LLM_CALLS: int = 8
    MAX_DOC_MB: int = 10
    MAX_PAGES: int = 100
    MAX_DOCS_PER_SESSION: int = 3
    MAX_QUESTIONS_PER_DAY: int = 25
    MAX_UPLOADS_PER_IP_DAY: int = 10
    RELEVANCE_THRESHOLD: float = 0.30
    CHUNK_TOKENS: int = 450
    CHUNK_OVERLAP: int = 80
    # --- Retrieval quality (v3 BYOK architecture) -------------------------
    # RRF over-fetches RETRIEVAL_POOL fused candidates; the open-source
    # cross-encoder rerank (FlashRank) then cuts them to RERANK_TOP_K for the
    # answerer. RERANK_ENABLED=false (or a missing flashrank install) degrades
    # to the plain RRF top-RERANK_TOP_K — the original E3 behaviour.
    RERANK_ENABLED: bool = True
    RERANK_TOP_K: int = 6
    RETRIEVAL_POOL: int = 12
    # The rolling window for the per-day question quota (the "day" in
    # MAX_QUESTIONS_PER_DAY). Since auth landed, accounts and their documents
    # persist indefinitely; this no longer governs data expiry.
    SESSION_TTL_HOURS: int = 24
    EMBED_BATCH_SIZE: int = 100

    @model_validator(mode="after")
    def _require_keys_in_prod(self) -> "Settings":
        """Fail fast in prod on any missing required key; warn-only in dev.

        Errors degrade, never break: a half-configured *dev* box should still
        boot so the developer can work on the parts that are wired up. A
        half-configured *prod* box must never accept traffic.
        """
        missing = [k for k in REQUIRED_IN_PROD if not getattr(self, k)]
        if not missing:
            return self
        if self.ENV == "prod":
            raise ValueError(f"Missing required config in prod: {', '.join(missing)}")
        _log.warning(
            "Config incomplete (ENV=%s): missing %s — dev boot continues.",
            self.ENV,
            ", ".join(missing),
        )
        return self


@lru_cache
def get_settings() -> Settings:
    """Lazily-built, cached settings singleton."""
    return Settings()
