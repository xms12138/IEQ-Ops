# TECH_STACK.md

Technology decisions and rationale for IEQ-Ops.

**Authority:** Per CLAUDE.md, this file wins for **specific tool choices**;
CLAUDE.md wins for **principles**. Per-node LLM model selection is owned by
[`ops/llm_routing.md`](ops/llm_routing.md), not here.

---

## Selection table

| Layer | Choice | Why | Rejected |
|---|---|---|---|
| Language / runtime | Python 3.11+ (uv-managed); C++ on ESP32 for firmware | StrEnum/typing; uv auto-fetches 3.11 even on a 3.10 host | — |
| Package management | **uv** | Fast, single lockfile, manages the interpreter | pip+venv (no lockfile), poetry (slower) |
| Orchestration | **LangGraph** `StateGraph` | Explicit graph + Postgres-persisted state + `interrupt()` for Tier 3 | LangChain `Chain`/`AgentExecutor` (Hard #6/#7); AutoGen/CrewAI/MetaGPT (out of scope) |
| LLM — cloud reasoning | **deepseek-v4-pro** | Planner DAG, Reflector induction; V3 successor (routing override A) | local 8B (fabricates — A4.5, Hard #12) |
| LLM — cloud fast | **deepseek-v4-flash** | Specialist decompose/grade/generate, Conversational | — |
| LLM — local | **Qwen3-8B** (Phase 6; dev → flash via override B) | Threshold/numeric/JSON nodes off the cloud hot path | — |
| API client | **openai** SDK | DeepSeek is OpenAI-API-compatible | bespoke httpx wrapper |
| Embedding | **BGE-M3** | Multilingual, 8K ctx, dense+sparse capable | OpenAI embeddings (cost/offline) |
| Reranker | **bge-reranker-v2-m3** | Precision reranking; reused for episodic recall in Phase 2 | — |
| Sparse retrieval | **BM25** | Dual-path recall with dense | — |
| RAG technique | **Anthropic Contextual Retrieval** (prefix injection) | Recovers chunk context lost by splitting | naive chunking; GraphRAG (out of scope) |
| Vector DB | **Qdrant** | Dedicated ANN + payload filtering; self-host | pgvector (weaker ANN at scale); Pinecone (cost/offline) |
| Relational + checkpoint | **Postgres 16** | LangGraph `PostgresSaver` (15-min suspend survives restart) + ticket CRUD | SQLite (no concurrent durability) |
| Time-series | **InfluxDB** (Phase 5; simulator until then) | Sensor history, downsampling | Postgres-only (poor TS ergonomics) |
| Observability | **LangFuse v2** (self-host, single-Postgres) | Nested traces per incident/node | v3 (adds ClickHouse/Redis/MinIO — overkill single-node) |
| Tool protocol | **FastMCP** — 4 servers (sensor/actuator/rag/ticket) | Type-safe Pydantic I/O for security-critical tools | ad-hoc function calls (no schema boundary) |
| Config | **pydantic-settings** | Typed `.env`, fail-loud on missing secret | os.environ |
| Logging | **structlog** (JSON) | Per-invocation structured logs → LangFuse | stdlib logging |
| Lint / format / types | **ruff** + **mypy --strict** (on `core/`) | Fast lint+format; strict typing on the brain | black+flake8 (slower) |
| Sensor messaging | **MQTT** (Phase 5) | RPi → ingest decoupling | direct HTTP POST |
| Frontend | **FastAPI** gateway + minimal panel (HTMX or Next.js) (Phase 5) | Incident view + Tier 3 approval | heavy SPA |
| Evaluation | **IEQ-Bench** (200 tasks); dual judge **GPT-4o + Claude Sonnet 4.6** | No claim without numbers | single judge (bias) |

## Hardware

Raspberry Pi 4 + SCD40 (CO₂) / DHT22 (temp+RH) / BH1750 (lux) / microphone ·
controllable actuator (smart plug / WiFi bulb / ESP32 fan) ·
**RTX 3060 Laptop GPU, 6 GB VRAM** for local inference (confirmed via nvidia-smi).

---

## Key decisions expanded

### LangGraph only
Three independent graphs + one shared subgraph (see CLAUDE.md "Graph Topology").
`Chain`/`AgentExecutor`/`create_react_agent` are banned (Hard #6/#7) — the
Plan-and-Execute + ReWOO planner and the 5-node Agentic RAG loop are custom graphs.

### DeepSeek over the OpenAI SDK
DeepSeek exposes an OpenAI-compatible endpoint, so the `openai` client points at
`api.deepseek.com`. V3 was retired upstream (2026-05-25); see routing override A
in `ops/llm_routing.md`. Both v4 models return `reasoning_content`, so latency
budgets in the routing table must be re-measured, not trusted as-is.

### Retrieval is deterministic; intelligence lives in the Specialist
`mcp-rag-server` runs BM25 + BGE-M3 dual recall → bge-reranker-v2-m3 → returns
chunks. **No LLM inside it** (Hard #9). Decompose / grade / rewrite / generate are
Specialist subgraph nodes, routed per `ops/llm_routing.md`.

---

## ✅ Resolved spike: 6 GB VRAM coexistence (measured 2026-05-25)

Measured on the real RTX 3060 (6 GB, shared Windows+WSL2) via
[`ops/scripts/vram_spike.py`](ops/scripts/vram_spike.py) plus the ollama runbook at
the bottom of that file. Embedders at fp16; Qwen3-8B served by Windows ollama.

| Resident set | Physical-card VRAM | Retrieve latency (1 query + 32-pair rerank) |
|---|---|---|
| Windows desktop idle (baseline) | ~1.2 GB | — |
| + BGE-M3 + reranker, **GPU fp16** | **4.0 GB** (peak) | **98 ms** ✅ |
| BGE-M3 + reranker, **CPU fp32** | (off-GPU) | **3 763 ms** ❌ (7.5× over budget) |
| Qwen3-8B alone (ollama) | **5.6 GB** | — (already spills ~2.1 GB to CPU to fit) |

**Three findings, all measured:**
1. **All-resident is impossible — harder than the back-of-envelope estimate.**
   Qwen3-8B alone pins 5.6/6.1 GB and ollama already offloads ~2.1 GB of layers to
   CPU RAM to fit (`size` 6.6 GB vs `size_vram` 4.5 GB). No room for *any* co-resident
   GPU model, let alone two embedders.
2. **Retrieve must run on GPU, not CPU.** CPU fp32 reranking of 32 candidates takes
   3.6 s — 7.5× over the Specialist's `< 500 ms` budget; GPU fp16 does it in 98 ms.
   This **overturns douluo's CPU-embedder choice**: douluo uses a lightweight bge-small
   with no latency floor, IEQ-Ops uses BGE-M3 against a real budget, so CPU is out.
3. **GPU-resident retrieve is cheap.** BGE-M3 + reranker at fp16 peak at only 4.0 GB
   (2.1 GB headroom) and load in ~9 s.

**Loading strategy (decided):**
- **Dev phase (Phase 0–5, routing override B → Qwen on cloud flash):** the GPU runs
  only the retrieve stack (BGE-M3 + reranker, fp16, 4.0 GB). No contention — usable today.
- **Phase 6 (local Qwen goes live):** Qwen (5.6 GB) and retrieve (4.0 GB) cannot
  co-reside, and retrieve cannot fall back to CPU. → **Time-share the GPU via ollama
  `keep_alive`:** the Monitor's 5-min loop loads Qwen (10 s cold-load, comfortably inside
  the cadence); incident handling unloads Qwen and loads the retrieve stack (~9 s). The
  two never need the GPU in the same instant. Cold-load cost is charged to the 5-min tick
  and the off-hot-path incident pipeline, never to the `< 500 ms` retrieve step (which
  only times resident-model inference). Validate the swap orchestration at Phase 6 start.

---

## See also

- [`CLAUDE.md`](CLAUDE.md) — principles, hard constraints, graph topology
- [`ops/llm_routing.md`](ops/llm_routing.md) — authoritative per-node model selection
- [`EXECUTION_PLAN.md`](EXECUTION_PLAN.md) — phased roadmap
