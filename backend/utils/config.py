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

# Keys that MUST be present before prod traffic. DocChat has no auth/payments —
# only the LLM gateways and the two data stores are load-bearing.
REQUIRED_IN_PROD: tuple[str, ...] = (
    "OPENROUTER_API_KEY",
    "GROQ_API_KEY",
    "QDRANT_URL",
    "QDRANT_API_KEY",
    "UPSTASH_URL",
    "UPSTASH_TOKEN",
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
    # Gemini models served VIA OpenRouter (one gateway, one key); Groq is the
    # failover (ARCHITECTURE §4). The key for each model is derived from its
    # provider prefix in llm_router._key_for.
    REWRITER_MODEL: str = "openrouter/google/gemini-3.1-flash-lite-preview"
    ANSWERER_MODEL: str = "openrouter/google/gemini-3-flash-preview"
    EMBED_MODEL: str = "openrouter/google/gemini-embedding-001"

    # --- Provider credentials -------------------------------------------
    OPENROUTER_API_KEY: str | None = None  # primary gateway (all LLM + embeddings)
    GROQ_API_KEY: str | None = None  # failover provider

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
