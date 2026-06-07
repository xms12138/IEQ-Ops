# IEQ-Ops

> Autonomous Building Operations Multi-Agent System
> CASA0022 dissertation · MSc Connected Environments · UCL CASA

**Status: 🚧 active development — Phases 0–3 complete; Phase 4 (IEQ-Bench eval + baseline) in progress.** The end-to-end incident loop runs on the simulator (monitor → … → verifier, with 15-min suspend/restart); three-tier memory + weekly reflection are in place.

A 24/7 self-running multi-agent system that monitors indoor environmental quality
(IEQ) sensors, autonomously diagnoses anomalies, executes graded interventions,
verifies outcomes, and distills experience into reusable SOPs.

This is **not** a chatbot over sensor data. It is an always-on autonomous operator:
it produces incidents, makes decisions, acts on physical devices, validates results,
and asks humans only for high-risk approvals.

## Architecture at a glance

Three independent LangGraphs over a Postgres-persisted state machine:

- **MainIncidentGraph** (hot path, every 5 min) — `monitor → memory_retrieve → planner → dispatch → specialist → critic → autonomy_gate → action → (15-min suspend) → verifier`
- **ReflectionGraph** (Sundays 03:00) — consolidates episodic memory into semantic facts + procedural SOPs
- **ConversationalGraph** (on-demand) — memory-first operator Q&A

Plus a shared **SpecialistSubgraph** — the 5-node Agentic RAG loop (`decompose → retrieve → grade → rewrite → generate`).

LLM routing is **per-node**, not per-agent: local Qwen3-8B for threshold/JSON/numeric
nodes, cloud DeepSeek for reasoning-heavy nodes. See [`ops/llm_routing.md`](ops/llm_routing.md).

Full design: [`CLAUDE.md`](CLAUDE.md) · roadmap: [`EXECUTION_PLAN.md`](EXECUTION_PLAN.md) · problems & retrospective: [`DEVLOG.md`](DEVLOG.md)

## Hardware

Raspberry Pi 4 + SCD40 (CO₂) / DHT22 / BH1750 / mic · controllable actuator
(smart plug / WiFi bulb / ESP32 fan) · RTX 3060 (6 GB) for local inference.

## Quickstart (dev)

```bash
# 1. Install dependencies (uv auto-fetches Python 3.11)
uv sync

# 2. Configure secrets
cp .env.example .env   # then fill in DEEPSEEK_API_KEY etc.

# 3. Bring up infrastructure (Postgres + Qdrant + LangFuse)
docker compose up -d

# 4. Lint + type-check
uv run ruff check .
uv run mypy            # strict, on core/
```

> ✅ Steps 1–4 pass. The end-to-end incident loop runs on the simulator as of Phase 1; see [`EXECUTION_PLAN.md`](EXECUTION_PLAN.md) for the current phase.

## Q&A butler (问答管家 — Q&A-first MVP)

A voice/text room butler that answers questions about the room by querying the
system's own data — current readings, normal-range checks, history stats, past
incidents, and learned facts. It does **not** call RAG/embeddings: range checks ride
on `sensing/thresholds.py` (the same truth the Monitor judges against), and the agent
fetches only the sources a question needs (one cheap flash classifies intent, a second
flash grounds the answer). Voice is a cascade (STT → text LLM → TTS); the MVP uses the
browser's Web Speech API, so no voice key is needed.

```bash
# 0. Infra + deps as in Quickstart (docker compose up -d; uv sync; .env filled)

# 1. Grow some history (fast demo: 10s interval) — leave running in a terminal
SAMPLE_INTERVAL_SECONDS=10 uv run python -m ops.sampler

# 2. (optional) Seed incident history so "recent anomalies" has data
uv run python -m ops.scripts.demo co2_spike

# 3. Start the web UI, then open http://localhost:8000
uv run uvicorn frontend.api.main:app --reload
```

Ask: “现在 CO2 和温度多少” · “现在温度在正常范围内吗” · “过去 24 小时 CO2 平均和最高” ·
“最近有没有异常” · “帮我把空调打开”（read-only → politely declined）.

Deferred until after the Q&A path lands: the always-on 5-min incident loop + progress
panel, remote embeddings, real voice API, real hardware. The butler is built
RPi-friendly — pure-Python app + remote flash API, no local models / no torch.

## License

MIT
