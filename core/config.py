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

    # ── LLM resilience (core/router.py) ──
    # Per-request timeout (seconds) on the OpenAI client. The SDK default is 600 s — far
    # too long for an unattended loop: a hung connection would block a 5-min scan for ten
    # minutes. Bound it so the router falls through to its model fallback promptly. Generous
    # enough for a reasoning-tier (pro) call; lower only if the hot path must stay snappier.
    llm_timeout_s: float = 120.0
    # In-SDK retries per model BEFORE the router tries its fallback model. The OpenAI client
    # retries connection errors / 429 / 5xx with exponential backoff; this is the first line
    # against a transient cloud blip, the model fallback is the second.
    llm_max_retries: int = 2

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

    # ── Exhibit / closed-loop pacing ──
    # The live exhibit stands the simulator in for the physical world, which only evolves
    # via RoomState.advance_minutes() — never wall-clock. So the scheduler's resume must
    # fast-forward the simulator across the verify window before the Verifier reads;
    # otherwise it sees the injected anomaly value unchanged → a false "missed" → a needless
    # replan in front of the audience. Three knobs (defaults ARE the exhibit config, so the
    # Pi needs no override — flip these only for the paper's true-15-min runs or once real
    # hardware feeds readings):
    #   exhibit_mode          — compress the wall-clock resume wait (a visitor can't stand
    #                           for the real 15-min window) down to verify_window_seconds.
    #   verify_window_seconds — wall-clock seconds the scheduler waits before resuming a
    #                           suspended thread under exhibit_mode (~90 s reads as "the
    #                           system is observing the effect" without dragging).
    #   sensor_source         — "sim" | "hardware". Only "sim" fast-forwards the room on
    #                           resume; once the Arduino feeds real readings the world moves
    #                           on its own and the scheduler must NOT touch the simulator.
    exhibit_mode: bool = Field(
        default=True, validation_alias=AliasChoices("exhibit_mode", "ieq_exhibit_mode")
    )
    verify_window_seconds: int = Field(
        default=90,
        validation_alias=AliasChoices("verify_window_seconds", "ieq_verify_window_seconds"),
    )
    sensor_source: str = Field(
        default="sim", validation_alias=AliasChoices("sensor_source", "ieq_sensor_source")
    )

    #   sim_ambient — exhibit only. An idle simulated room reads from sensing/ambient (a
    #     diurnal + drift model, held inside every threshold) so the gauges live instead of
    #     sitting on one frozen number; an injected demo still gets the real physics. Off by
    #     default because IEQ-Bench reads the same simulator and must stay deterministic.
    sim_ambient: bool = Field(
        default=False, validation_alias=AliasChoices("sim_ambient", "ieq_sim_ambient")
    )

    # ── Hardware sensor node (Arduino MKR1010 → MQTT → sensing/ingest → sensor_readings) ──
    # Consumed only when sensor_source == "hardware". The ingest writer subscribes to the
    # broker and runs sensing/calibration on each raw frame before record_reading().
    mqtt_host: str = "localhost"  # Mosquitto broker — the Pi itself on the exhibit
    mqtt_port: int = 1883
    mqtt_topic: str = "ieq/readings"
    # SCD30 self-heating: the chip sits on the MKR's regulator and reads several degC high
    # (~36 °C raw against a ~26 °C room). Calibration subtracts this fixed offset on the Pi
    # side (rather than setTemperatureOffset in firmware) so it tunes without reflashing.
    temp_offset_c: float = 0.0
    # Grove Light v1.1 / Sound v1.6 send raw 0–1023 ADC counts, NOT lux/dBA. Calibration maps
    # raw→engineering units by linear interpolation between two measured extremes. While a
    # channel's two raw extremes are equal (the 0/0 default) it is treated as UNCALIBRATED and
    # sensing/calibration returns an in-band safe value, so the Monitor never false-fires on a
    # raw count that has no physical meaning yet. Fill these once the extremes are measured.
    light_raw_dark: float = 0.0  # raw count, dark room
    light_raw_bright: float = 0.0  # raw count, under task lighting
    light_lux_dark: float = 0.0  # lux at light_raw_dark
    light_lux_bright: float = 500.0  # lux at light_raw_bright
    sound_raw_quiet: float = 0.0  # raw count, quiet room
    sound_raw_loud: float = 0.0  # raw count, loud noise
    sound_db_quiet: float = 35.0  # dBA at sound_raw_quiet
    sound_db_loud: float = 75.0  # dBA at sound_raw_loud

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
