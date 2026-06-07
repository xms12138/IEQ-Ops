# CLAUDE.md

This file is the project constitution for Claude Code. Read this before any non-trivial task.

---

## Project Identity

**Name (working title):** IEQ-Ops — Autonomous Building Operations Multi-Agent System

**One-line pitch:** A 24/7 self-running multi-agent system that monitors indoor environmental quality (IEQ) sensors, autonomously diagnoses anomalies, executes graded interventions, verifies outcomes, and continually distills experience into reusable SOPs.

**This is NOT:** a chatbot, a Q&A interface over sensor data, or a dashboard with LLM cosmetics.

**This IS:** an always-on autonomous operator that produces incidents, makes decisions, takes actions on physical devices, validates results, and asks humans only for high-risk approvals.

---

## Project Context

- **Author:** Zihang He, MSc Connected Environments, UCL CASA
- **Submission:** CASA0022 dissertation, December 2026
- **Secondary purpose:** flagship portfolio project for 2027届 autumn campus recruitment in China (LLM application engineer / agent engineer roles at ByteDance, Alibaba, DeepSeek, Zhipu, Moonshot; SOE track at 三桶油 / 中信 / 中国电科)
- **Hardware:** Raspberry Pi 4 + SCD40 (CO2) + DHT22 + BH1750 + microphone; one or more controllable actuators (smart plug / WiFi bulb / ESP32 fan); RTX 3060 (6GB) for local LLM inference

---

## Architecture in One Paragraph

The system runs two parallel loops on a LangGraph state machine persisted in Postgres. The **Monitoring Loop** fires every 5 minutes: a Monitor Agent uses local Qwen3-8B **for pure threshold judgement only — never diagnosis** — to scan all sensors via an MCP sensor server, emit a strictly-schema'd anomaly record (`{anomaly, sensor, value, rule_violated}`), and create Incidents. For each incident, a Memory Agent retrieves similar past cases from Episodic Memory, then a Planner Agent (cloud DeepSeek-V3, reasoning-depth-critical) produces a subtask DAG using a Plan-and-Execute + ReWOO hybrid. Specialist Agents (AirQuality / Thermal / Lighting / Acoustic) execute subtasks with domain-restricted tools and **Agentic RAG**. **The agentic loop runs inside the Specialist** as five distinct LangGraph nodes with separate model selection: `decompose` (cloud V4-Flash) splits the subtask into sub-queries; `retrieve` (no LLM) calls `mcp-rag-server`; `grade` (**cloud V4-Flash, mandatory**) applies a Self-Reflective faithfulness + completeness judgement on chunks; `rewrite` (local Qwen3-8B, short-string transform) crafts a new query if grade fails; and `generate` (**cloud V4-Flash, mandatory**) synthesises the final answer with strict groundedness to retrieved chunks. Retries are capped at 3 per sub-query. **The MCP RAG server itself contains no LLM**; it only executes the deterministic retrieval pipeline (BM25 + BGE-M3 dual-path retrieval, bge-reranker-v2-m3 precision reranking, and Anthropic Contextual Retrieval prefix injection). A Critic Agent (local Qwen3-8B) validates the primary diagnosis before the autonomy gate. **Plan B (state isolation forces this):** the parent critic cannot see the subgraph's `retrieved_chunks`, so instead of source trace-back it runs a deterministic plausibility floor on the `expected_outcome` plus an LLM judgement of the diagnosis's internal coherence and outcome-to-diagnosis fit; an incoherent or physically implausible diagnosis fails the incident without acting (Phase 3 will route failure to replan). Specialist answers must declare expected outcome as a typed schema (`{target_metric, target_value, target_time_min}`) so the downstream Verifier can run locally. Interventions go through tiered autonomy gating (Tier 1 auto / Tier 2 notify / Tier 3 human approval via LangGraph `interrupt()`), then an Action Layer executes via an MCP actuator server. A Verifier Agent (local Qwen3-8B) checks the schema'd outcome 15 minutes later and either closes the incident (writing the trajectory to Episodic Memory) or triggers replan. The **Reflection Loop** runs every Sunday 03:00, consolidating Episodic Memory into Semantic Memory (building-specific facts) and Procedural Memory (preemptive SOPs); both Reflector calls are **cloud DeepSeek-V3, never local** — Week 8 vs Week 1 improvement evidence depends on this. Reflection is chunked by incident type to stay inside context limits. A Conversational Agent (cloud V4-Flash, streaming, escalates to V3 on low self-confidence) serves human queries with a memory-first dispatch strategy. **Per-node model selection, ablate conditions, fallback paths, and latency budgets are authoritative in `ops/llm_routing.md`.**

---

## Graph Topology

The system compiles into **3 independent LangGraphs** plus **1 reusable subgraph**. They share no in-memory state at runtime; cross-graph communication is only through Postgres + Qdrant.

- **MainIncidentGraph** — hot path, triggered every 5 min by cron + Monitor anomalies. Node order: `monitor → memory_retrieve → planner → dispatch → {airquality|thermal|lighting|acoustic} → critic → autonomy_gate → action → (15-min checkpoint suspend) → verifier`. Persists to Postgres so the 15-min verification step survives restarts.
- **ReflectionGraph** — cold path, triggered every Sunday 03:00 by cron. Reads Episodic Memory, writes Semantic + Procedural Memory. Chunked by incident type to stay inside context limits.
- **ConversationalGraph** — on-demand, triggered by user HTTP/WS. Memory-first dispatch; V4-Flash streams the answer, escalates to V3 on low self-confidence.
- **SpecialistSubgraph** — the Agentic RAG 5-node loop (`decompose → retrieve → grade → rewrite → generate`). **One compiled instance, shared by all four Specialist domains** via a `domain` parameter that selects the RAG corpus slice and tool subset. Lives in `agents/specialists/builder.py`; the four `agents/specialists/{domain}.py` files are thin wrappers that invoke it with the right `domain`.

**MemoryAgent is not a LangGraph node.** Memory retrieval is a deterministic Qdrant query implemented as `memory/episodic.py::retrieve_similar()` and called inline from the `planner` node. Wrapping a single LLM-free query in a node would be theater.

**Subgraph state isolation.** The Specialist subgraph has its own Pydantic state schema (`SpecialistState`). Only `subtask` enters from the parent and only `final_diagnosis` returns to the parent. Bulky intermediate fields (`retrieved_chunks`, `grade_history`, `rewrite_count`) never reach the parent's checkpoint — this is the primary mechanism preventing state bloat in `MainIncidentGraph`.

**Subgraphs compile at module-load time, not on demand.** `SpecialistSubgraph` is `.compile()`'d once when `core/graph.py` is imported, then invoked from the four wrapper nodes via `SPECIALIST_SUBGRAPH.invoke(child_input, config=config)`. Recompiling per incident is forbidden — pass `config` through to keep LangFuse traces nested.

---

## Core Architectural Principles

1. **Autonomy over chat.** The system runs whether or not humans are watching. Chat is a thin facade on top of an autonomous core, not the core itself.
2. **Closed loop, not open prompt.** Every intervention has a verification step. Failed interventions trigger replan, not silence.
3. **Job isolation, not agent theater.** Multi-agent design is for tool / context / RAG-slice isolation. Agents do not "debate"; they have non-overlapping responsibilities.
4. **Memory makes the system smarter over time.** Three-tier memory (episodic / semantic / procedural) with weekly reflection consolidation. Week 8 must measurably outperform Week 1 on recurring patterns.
5. **Tiered autonomy with hard safety floors.** Reversibility, energy impact, and occupant disturbance determine the autonomy tier. Tier 3 actions block on `interrupt()` and persist to Postgres until human approval.
6. **Hybrid CLI + MCP + Skills.** MCP for type-safe security-critical tools (sensors, actuators, RAG, tickets). CLI for agent-internal scratchpad operations. Skills for progressive-disclosure of specialist knowledge.
7. **Node-level LLM routing, not agent-level.** Capability profiling (see `ops/llm_routing.md`) drives selection per LangGraph node, not per agent. Local Qwen3-8B is reserved for nodes that are pure threshold judgement, JSON extraction, token-level comparison, or short-string rewrite (Monitor anomaly detection, Verifier numeric comparison, Critic plausibility floor + coherence check, Specialist query rewrite). Cloud LLMs (DeepSeek-V3 / V4-Flash) are mandatory for any node that requires multi-fact induction, faithfulness to retrieved context, completeness judgement, or causal reasoning (Planner DAG generation, Specialist decompose / grade / generate, Reflector semantic + procedural consolidation, Conversational). Reflection is **not** a routine task and must never run on local. Cost is a first-class design metric, but capability floors override cost — see `ops/llm_routing.md` for the per-node ablate conditions and fallback paths.
8. **Evaluation is part of the system, not an afterthought.** Every code change runs against IEQ-Bench. Online traces flow through LangFuse. No claim without numbers.

---

## Naming Conventions

- **Agents:** `{Role}Agent` PascalCase. `MonitorAgent`, `AirQualityExpert`, `Critic`, `Verifier`, `Reflector`.
- **LangGraph parent graphs:** `{Name}Graph` PascalCase. `MainIncidentGraph`, `ReflectionGraph`, `ConversationalGraph`.
- **LangGraph subgraphs:** `{Name}Subgraph` PascalCase. `SpecialistSubgraph`.
- **Infrastructure nodes** (no LLM — pure routing/scheduling/hydration): snake_case. `dispatch`, `autonomy_gate`, `memory_retrieve`, `hydrate_placeholders`, `chunk_by_type`.
- **MCP servers:** `mcp-{domain}-server`. `mcp-sensor-server`, `mcp-actuator-server`, `mcp-rag-server`, `mcp-ticket-server`.
- **State fields in LangGraph:** snake_case. `incident_id`, `current_plan`, `replan_count`.
- **ReWOO placeholder refs in subtask goals:** `#{subtask_id}.{field}`. e.g. `#S1.diagnosis`, `#S2.thermal_impact`. Resolved by `hydrate_placeholders` before the dependent subtask runs.
- **Skills:** `skills/{domain}-{action}/SKILL.md`. e.g. `skills/airquality-diagnosis/SKILL.md`.
- **Memory IDs:** `I-{date}-{room}-{type}` for incidents, `SF-{year}-W{week}-{seq}` for semantic facts, `SOP-{year}-{seq}` for procedures.

---

## Coding Standards

- **Language:** Python 3.11+ for everything except actuator firmware (C++ on ESP32 if used)
- **Type checking:** All function signatures use type hints. Pydantic for all LLM-facing schemas. `mypy --strict` on `core/` modules.
- **Testing:** pytest for unit tests on tools. Integration tests run against fake sensor data via the simulator. Do not write tests for prompts — use IEQ-Bench instead.
- **Logging:** structured JSON logs via `structlog`. Every agent invocation logs `{agent, incident_id, plan_id, step, tokens_in, tokens_out, latency_ms}`. Forward to LangFuse.
- **Secrets:** `.env` for development, never committed. `pydantic-settings` for typed config loading.
- **Dependencies:** `uv` for package management (faster than pip + handles lockfile). `pyproject.toml` only.
- **Formatting:** `ruff format` + `ruff check`. No exceptions.

---

## Repository Layout


```

ieq-ops/
├── CLAUDE.md                  # this file
├── EXECUTION_PLAN.md          # 12-week task list
├── TECH_STACK.md              # technology decisions and rationale
├── README.md                  # public-facing project description
├── pyproject.toml
├── docker-compose.yml         # Postgres + LangFuse + Qdrant
├── .env.example
│
├── core/                      # the agent brain
│   ├── graph.py               # LangGraph StateGraph definition
│   ├── state.py               # global state schema (Pydantic)
│   ├── router.py              # local-vs-cloud LLM router
│   └── checkpointer.py        # Postgres checkpoint config
│
├── agents/                    # one file per agent role
│   ├── monitor.py
│   ├── planner.py
│   ├── specialists/
│   │   ├── builder.py         # shared SpecialistSubgraph factory (compiled once)
│   │   ├── airquality.py      # thin wrapper: invokes builder with domain="airquality"
│   │   ├── thermal.py         # thin wrapper: domain="thermal"
│   │   ├── lighting.py        # thin wrapper: domain="lighting"
│   │   └── acoustic.py        # thin wrapper: domain="acoustic"
│   ├── critic.py
│   ├── verifier.py
│   ├── reflector.py
│   └── conversational.py
│   # Note: no memory.py — memory retrieval is implemented as a function in
│   # memory/episodic.py and called inline from the planner node, not as a separate agent.
│
├── memory/                    # three-tier memory system
│   ├── episodic.py            # Qdrant-backed incident trajectories
│   ├── semantic.py            # building-specific facts (JSON + vectors)
│   └── procedural.py          # SOP templates with trigger conditions
│
├── rag/                       # standards knowledge base
│   ├── ingest.py              # PDF -> chunks -> contextual prefix -> embed
│   ├── retrieve.py            # BM25 + dense + reranker
│   └── corpus/                # ASHRAE / WELL / EN / WHO standards (gitignored)
│
├── mcp_servers/               # 4 independent MCP servers
│   ├── sensor/                # FastMCP, queries InfluxDB
│   ├── actuator/              # FastMCP, controls physical devices
│   ├── rag/                   # FastMCP, wraps rag/retrieve.py — stateless, no LLM
│   └── ticket/                # FastMCP, incident CRUD on Postgres
│
├── skills/                    # Anthropic-style progressive disclosure
│   ├── airquality-diagnosis/SKILL.md
│   ├── thermal-comfort-diagnosis/SKILL.md
│   ├── preemptive-ventilation/SKILL.md
│   └── compliance-check-ashrae/SKILL.md
│
├── sensing/                   # hardware + simulator
│   ├── hardware/              # RPi sensor reader, MQTT publisher
│   ├── simulator/             # physics-based CO2 / RC thermal model
│   └── ingest/                # MQTT -> InfluxDB writer
│
├── eval/                      # offline evaluation
│   ├── ieq_bench/             # 200-task benchmark (open-sourced to HF)
│   ├── judge.py               # dual LLM-as-judge (GPT-4o + Claude)
│   ├── runner.py              # parallel benchmark execution
│   └── reports/               # generated comparison tables and plots
│
├── frontend/                  # minimal operator dashboard
│   ├── app/                   # Next.js or plain HTML/HTMX
│   └── api/                   # FastAPI gateway
│
└── ops/
├── llm_routing.md         # authoritative per-node model selection table
├── prompts/               # versioned prompts, never inline
├── scripts/               # CLI utilities for ops
└── deployment/            # systemd units, cron, etc.

```

---

## Workflow Conventions

### When Claude Code is asked to add a new agent

1. Create `agents/{name}.py` with a class `{Name}Agent` exposing one method `run(state) -> state`.
2. Add the corresponding node + edges in `core/graph.py`.
3. Add the agent's prompt as a versioned file under `ops/prompts/{name}/v{n}.md` — never inline strings.
4. Add at least one IEQ-Bench task that exercises this agent.
5. Update this CLAUDE.md if the agent introduces a new architectural concept.

### When Claude Code is asked to add a new tool

1. Decide CLI vs MCP vs Skill (default to MCP if it touches physical devices, external APIs, or persistent state; CLI if it's an internal scratchpad operation).
2. If MCP: add to the relevant `mcp_servers/{domain}/` directory, expose via FastMCP `@tool` decorator, document the schema.
3. If a new MCP server: also update `core/router.py` connection list and `docker-compose.yml`.
4. If CLI: ensure the tool is in the agent's allowed-bash-list.
5. Always include a typed Pydantic schema for inputs and outputs.

### When Claude Code is asked to modify a prompt

1. Never edit the inline string. Find the prompt under `ops/prompts/{agent}/v{n}.md`.
2. Bump version: copy to `v{n+1}.md`, edit there.
3. Update the agent's prompt-loading code to point at the new version.
4. Run IEQ-Bench on the change and report deltas before merging.

### When Claude Code is asked to debug

1. First check LangFuse traces for the failing incident — most issues are visible there.
2. Then check Postgres `incidents` and `action_log` tables.
3. Only then read code. Code is rarely the problem; prompts and tool schemas usually are.

---

## Hard Constraints (Things Claude Code Must Never Do)

1. **Never call cloud LLM APIs from monitoring loop hot path.** Monitor scans run every 5 min on local Qwen3-8B; cloud calls fire downstream of incident creation (Planner / Specialist / Reflector / Conversational), which are off the hot path.
2. **Never bypass the autonomy gate.** Every actuator call goes through `Tier{1,2,3}` evaluation, even in dev mode.
3. **Never let an agent edit memory directly.** Memory writes go through dedicated `memory/` module functions with audit logging.
4. **Never inline prompts in agent code.** All prompts live in `ops/prompts/`.
5. **Never commit `.env`, `corpus/`, or `eval/reports/` raw outputs.** All in `.gitignore`.
6. **Never use LangChain's `Chain` or `AgentExecutor` classes.** LangGraph only.
7. **Never use `langchain.agents.create_react_agent`.** We have a custom Plan-and-Execute + ReWOO graph.
8. **Never reference leaked Claude Code source code in any commit, comment, or documentation.** Architecture inspiration comes from public reporting only (cite VentureBeat, 36kr, etc.).
9. **Never put LLM calls inside `mcp_servers/rag/`.** All query decomposition, self-reflective judgment, and query rewriting belong to the calling Specialist Agent. The RAG MCP server is a deterministic retrieval primitive.
10. **Never let MonitorAgent emit free-text diagnosis.** Its output schema is locked to `{anomaly: bool, sensor: str, value: float, rule_violated: str}`. Diagnosis is the Specialist's job. Capability evidence: local Qwen3-8B fabricates causal narratives when asked to interpret sensor anomalies (A4.5 closed-book Q16/Q17/Q22/Q23).
11. **Never route Specialist `grade` or `generate` nodes to local Qwen3-8B.** A4.5 measured a 14 pp hit-only gap on `generate` and "confidently says enough" failure mode on `grade`. Both must run on cloud V4-Flash minimum. Cost saving on these two nodes invalidates the IEQ-Bench claim and the closed-loop guarantee.
12. **Never route Reflector (semantic + procedural consolidation) to local Qwen3-8B.** A4.5 showed local 8B fabricates SOPs and misses common patterns in multi-incident induction. Week 8 vs Week 1 improvement is the dissertation's headline evidence — running this on local poisons Episodic→Semantic→Procedural memory and the contribution collapses. Cloud DeepSeek-V3 is mandatory.
13. **Never let a Specialist emit unstructured "expected outcome" text.** Every Specialist answer must include a typed `expected_outcome: {target_metric, target_value, target_time_min}` block. This is what makes Verifier safe to run on local Qwen3-8B — without the schema, Verifier requires cloud, breaking the latency budget on the 15-minute verification step.

---

## Out of Scope

These are explicitly NOT in scope and Claude Code should push back if asked to add them:

- Multimodal / vision (no camera analysis)
- Voice interface / TTS — **exception:** the Q&A butler's cloud-API CASCADE voice (STT → text LLM → TTS) is deliberately in scope; what stays out is end-to-end speech models and any device-side voice UI beyond the browser Web Speech demo.
- Browser agent / computer use
- Knowledge graph / Neo4j / GraphRAG
- AutoGen / CrewAI / MetaGPT (LangGraph only)
- RLHF / DPO / GRPO fine-tuning (SFT + LoRA only if Phase 8 happens)
- Federated learning / blockchain
- Multi-agent debate mechanisms
- Edge AI deployment to Jetson / NPU

---

## Success Criteria

By the time the dissertation is submitted, the system must:

- Run autonomously for ≥ 4 weeks at UCL CASA without human babysitting
- Auto-resolve ≥ 80% of detected incidents at Tier 1 (no human input)
- Score ≥ 75% task success on IEQ-Bench v1 (200 tasks)
- Beat GPT-4o + ReAct baseline by ≥ 10 percentage points on IEQ-Bench
- Demonstrate measurable improvement Week 8 vs Week 1 on recurring patterns (proving memory consolidation works)
- Have a public IEQ-Bench dataset on HuggingFace with documentation
- Have a polished GitHub repo (≥ 100 stars target) with reproducibility instructions

---

## When in Doubt

Re-read this file. Then re-read EXECUTION_PLAN.md. Then ask before assuming.

If something here conflicts with TECH_STACK.md, this file wins for **principles**, TECH_STACK.md wins for **specific tool choices**.
