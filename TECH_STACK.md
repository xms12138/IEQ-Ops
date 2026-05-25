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

## ⚠️ Open spike: 6 GB VRAM coexistence (Phase 0 item, not yet run)

**Question:** can Qwen3-8B + BGE-M3 + bge-reranker-v2-m3 stay resident together on
6 GB? Rough budget: Qwen3-8B at 4-bit ≈ 5–6 GB alone, BGE-M3 ≈ 2 GB, reranker ≈
2 GB → **all-resident is infeasible at 6 GB.** A loading strategy is mandatory.

**Mitigating reality:** dev-phase override B runs Qwen on cloud flash, so until
Phase 6 only BGE-M3 + reranker (~4 GB) need to be local — comfortably fits. The
three-way contention is a **Phase 6 problem**, to resolve before the autonomous run.

**Candidate strategy (to validate in the spike):**
- Qwen3-8B as **4-bit GGUF via Ollama/llama.cpp**, kept resident.
- BGE-M3 + reranker **time-shared** (load on demand) or **CPU-offloaded** — the
  monitoring loop only needs Qwen; RAG retrieval needs the embedders, and the two
  rarely fire in the same 100 ms.

**To measure:** peak VRAM with each combination resident; load/unload latency vs.
the Monitor's 5-min cadence and the Specialist's `< 500 ms` retrieve budget.
**Decision will be recorded here once the spike runs.**

---

## See also

- [`CLAUDE.md`](CLAUDE.md) — principles, hard constraints, graph topology
- [`ops/llm_routing.md`](ops/llm_routing.md) — authoritative per-node model selection
- [`EXECUTION_PLAN.md`](EXECUTION_PLAN.md) — phased roadmap
