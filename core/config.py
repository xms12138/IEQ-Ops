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

from pydantic import AliasChoices, Field
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

    # ── RAG retrieval tuning ──
    # Device for the BGE-M3 + reranker stack in mcp-rag-server. Default "cuda" (dev box
    # with the RTX 3060); the CPU-only exhibit Pi sets "cpu" in .env. Read here through
    # Settings (not a bare os.getenv) so systemd units pick it up from EnvironmentFile.
    # Accepts the legacy IEQ_RAG_DEVICE name too, so existing .env files keep working.
    rag_device: str = Field(
        default="cuda", validation_alias=AliasChoices("rag_device", "ieq_rag_device")
    )
    # Candidates the reranker scores. Default 30 = the eval/GPU baseline. The CPU-only
    # exhibit Pi sets this low (e.g. 5) in .env: the reranker forward is ~6 s/candidate
    # and the entire retrieve cost, so fewer candidates trades recall for latency. At 5
    # (== FINAL_TOP_K) the reranker only reorders the RRF top-5 rather than precision-
    # selecting from a larger pool — an accepted exhibit trade-off, not the eval path.
    rag_rerank_candidates: int = 30

    # ── LangFuse (observability) ──
    langfuse_host: str = "http://localhost:3000"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""

    # ── Sampling (lightweight history sampler — ops/sampler.py) ──
    sample_interval_seconds: int = 300  # demo: lower (e.g. 10) to grow a trend fast

    # ── Voice (cascade STT→LLM→TTS) — mock (browser Web Speech) | aliyun (百炼) ──
    voice_provider: str = "mock"  # mock (browser, no key) | aliyun (DashScope cascade)
    voice_api_key: str = ""  # legacy/reserved; aliyun reads dashscope_api_key below
    dashscope_api_key: str = ""  # 百炼/DashScope key — Qwen3-TTS realtime + Paraformer STT
    # Singapore (intl) endpoints — measured ~5 s faster than Beijing for the author.
    dashscope_ws_url: str = "wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime"  # TTS realtime
    dashscope_http_url: str = "https://dashscope-intl.aliyuncs.com/api/v1"  # STT (Qwen3-ASR) HTTP
    tts_model: str = "qwen3-tts-flash-realtime"  # Qwen3-TTS flash, streaming realtime
    tts_voice: str = "Jennifer"  # 詹妮弗 — American-drama female lead
    tts_language: str = "English"  # qwen-tts language_type
    asr_model: str = "qwen3-asr-flash"  # Qwen3-ASR (intl); batch file recognition via HTTP

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
