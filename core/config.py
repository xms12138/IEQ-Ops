"""Typed configuration loaded from `.env` via pydantic-settings.

Single source of truth for secrets and connection strings. The DeepSeek API
key has no default — a missing one fails loudly at startup rather than
surfacing mid-incident. Everything else gets a safe local-dev default
(override DATABASE_URL etc. in prod).

Usage:
    from core.config import get_settings
    settings = get_settings()
    client = OpenAI(api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url)
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # tolerate extra .env keys (e.g. legacy DEEPSEEK_MODEL)
    )

    # ── DeepSeek (OpenAI-API-compatible) ──
    deepseek_api_key: str
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model_pro: str = "deepseek-v4-pro"  # reasoning tier — Planner, Reflector
    deepseek_model_flash: str = "deepseek-v4-flash"  # fast tier — Specialist, Conversational

    # ── Postgres (checkpointer + ticket server) ──
    database_url: str = "postgresql://ieqops:changeme@localhost:5432/ieqops"

    # ── Qdrant (memory + RAG vectors) ──
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""

    # ── LangFuse (observability) ──
    langfuse_host: str = "http://localhost:3000"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""

    # ── Runtime ──
    env: str = "dev"  # dev | prod
    log_level: str = "INFO"

    @property
    def is_dev(self) -> bool:
        return self.env == "dev"


@lru_cache
def get_settings() -> Settings:
    """Cached singleton. First call reads `.env`; subsequent calls are free."""
    return Settings()  # type: ignore[call-arg]  # required fields come from env, not args
