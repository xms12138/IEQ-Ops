# LLM Routing — Per-Node Model Selection

> ## ⚠️ ROUTING OVERRIDE (active 2026-05-25)
>
> Two changes layered on top of the per-node table below. Env (`.env`): `DEEPSEEK_MODEL_PRO=deepseek-v4-pro`, `DEEPSEEK_MODEL_FLASH=deepseek-v4-flash`, base `https://api.deepseek.com`.
>
> **(A) PERMANENT — DeepSeek-V3 → `deepseek-v4-pro`.** DeepSeek retired V3 upstream; the API now exposes only `deepseek-v4-pro` and `deepseek-v4-flash` (confirmed 2026-05-25 via the API's own 400 error). `deepseek-v4-pro` is the official successor (≥ V3 capability), so nodes **#3 Planner** and **#7/#8 Reflector** run on `deepseek-v4-pro` in **both dev and target production**. The `Cloud DeepSeek-V3` cells below have been updated accordingly.
>
> **(B) STANDING POLICY — local-tier nodes run on `deepseek-v4-flash`.** The nodes the table marks **Local Qwen3-8B** (`#1 Monitor`, `#4d rewrite`, `#5 Critic`, `#6 Verifier`) run on `deepseek-v4-flash` in **both dev and production**. This is the active policy until the author wires a local Qwen3-8B client and switches these four nodes back — there is **no Phase 6 deadline** on that cutover. The local rationale, ablate conditions, and Qwen3-8B target in the per-node sections below are **retained** as the spec for that future switch-back, not deleted.
>
> **Known constraint breach (accepted, ongoing):** routing `#1 Monitor` to cloud is a known, ongoing deviation from `CLAUDE.md` Hard Constraint #1 (no cloud in the monitoring hot path). Restoring #1 compliance is deferred to the future local cutover above — it is **not** gated on Phase 6.
>
> **Latency caveat:** both `deepseek-v4-flash` and `deepseek-v4-pro` return `reasoning_content` (reasoning models), so real latency exceeds the table's `< 5 s` / `< 3 s first token` budgets. Don't validate latency claims against them; re-measure with production routing.
>
> **Not covered:** `#11 eval.judge` (GPT-4o + Claude, no keys yet — Phase 4 concern).

**Authority:** This file is the canonical source for which LLM runs at each LangGraph node in IEQ-Ops. `CLAUDE.md` references this file; `core/router.py` must implement it.

**Why this exists:** Agent-level routing ("Monitor=local, Planner=cloud") is too coarse. The same agent can have nodes with very different capability requirements (e.g. Specialist's `grade` is reasoning-heavy, `rewrite` is a short-string transform). Routing happens **per node**, driven by capability profiling (A4.5 experiment) and cost.

**Decision rule:** If a node requires (a) faithfulness to long context, (b) multi-fact induction, (c) completeness/sufficiency judgement, or (d) causal reasoning → cloud. Otherwise (threshold check, JSON extraction, token-level comparison, short-string rewrite) → local Qwen3-8B is acceptable, but every "local" choice must have a documented ablate condition under which it gets re-evaluated.

---

## The 11 Call Points

| # | Node | Loop | Freq | Input → Output | Model | Latency budget | Hot path? |
|---|------|------|------|----------------|-------|----------------|-----------|
| 1 | `MonitorAgent.scan` | Monitoring | 8640/mo (every 5 min) | sensor readings + threshold rules → `{anomaly, sensor, value, rule_violated}` | **Local Qwen3-8B** *(currently `deepseek-v4-flash` — override B)* | < 5 s | **Yes** (hard floor) |
| 2 | `MemoryAgent.retrieve` | Incident | ~300/mo | incident description → top-k episodic cases | **No LLM** (embedding only, BGE-M3) | < 200 ms | No |
| 3 | `PlannerAgent.plan` | Incident | ~300/mo | incident + similar cases + specialist list → subtask DAG | **Cloud `deepseek-v4-pro`** (was DeepSeek-V3) | < 30 s (first DAG node visible) | No |
| 4a | `Specialist.decompose` | Per-subtask | ~300/mo | subtask → ≤3 sub-queries | **Cloud V4-Flash** | < 5 s | No |
| 4b | `Specialist.retrieve` | Per-sub-query | ~1500/mo | sub-query → top-5 chunks | **No LLM** (`mcp-rag-server`) | < 500 ms | No |
| 4c | `Specialist.grade` ★ | Per-sub-query | ~1500/mo | (sub-query, chunks) → `{sufficient: bool, missing: [...]}` | **Cloud V4-Flash (mandatory)** | < 5 s | No |
| 4d | `Specialist.rewrite` | Per-failed-grade | ~500/mo | (old query, grade feedback) → new query | **Local Qwen3-8B** (ablate-watched) *(currently `deepseek-v4-flash` — override B)* | < 3 s | No |
| 4e | `Specialist.generate` ★ | Per-subtask | ~300/mo | accumulated chunks + subtask → grounded answer + `expected_outcome` block | **Cloud V4-Flash (mandatory)** | < 10 s | No |
| 5 | `CriticAgent.validate` | Per-answer | ~300/mo | (diagnosis, expected_outcome) → unsupported-claim list | **Local Qwen3-8B (Plan B: deterministic floor + coherence judgement, no chunk trace-back)** *(currently `deepseek-v4-flash` — override B)* | < 5 s | No |
| 6 | `VerifierAgent.check` | Post-action | ~300/mo | (pre/post sensor readings, `expected_outcome` schema) → `{verdict, delta}` | **Local Qwen3-8B** (depends on Hard Constraint #13) *(currently `deepseek-v4-flash` — override B)* | < 5 s | No |
| 7 | `Reflector.semantic` ★ | Weekly | 4/mo | one week of incidents (chunked by type) → semantic facts | **Cloud `deepseek-v4-pro` (mandatory)** (was DeepSeek-V3) | < 5 min total | No |
| 8 | `Reflector.procedural` ★ | Weekly | 4/mo | one week of successful trajectories → SOP templates (queued for human sign-off) | **Cloud `deepseek-v4-pro` (mandatory)** (was DeepSeek-V3) | < 5 min total | No |
| 9 | `ConversationalAgent.respond` | On-demand | ~200/mo | user query + memory-first dispatch → answer | **Cloud V4-Flash, streaming; escalate to V3 if self-confidence < 0.7** | < 3 s first token | No |
| 10 | `rag.ingest.contextual_prefix` | One-shot | per corpus update | (chunk, full document) → 50–100 word prefix | **Cloud V4-Flash + implicit KV cache** (Track A validated, 96.4 % cache hit) | n/a | No |
| 11 | `eval.judge` | Per-commit | ~20 commits/mo × 200 tasks | (agent answer, expected) → hit/partial/miss | **GPT-4o + Claude Sonnet 4.6 dual-judge** | n/a | No |

★ = A4.5 hard constraint. Switching to local invalidates a dissertation success criterion. See `CLAUDE.md` Hard Constraints #11, #12.

---

## Per-Node Rationale, Ablate Condition, Fallback

### #1 MonitorAgent.scan — Local Qwen3-8B

- **Rationale:** Pure threshold + rule judgement. No retrieval, no narrative. Local 8B handles JSON-shape output reliably. Also forced by Hard Constraint #1 (no cloud in hot path).
- **Ablate condition:** Never ablate to cloud. If "more intelligence" is wanted in monitoring, push the new logic into deterministic Python rules in `sensing/`, not the LLM.
- **Fallback:** Qwen3-8B unavailable (RPi OOM, GPU down) → bypass LLM entirely, run pure-Python threshold checks. Never call cloud here.

### #2 MemoryAgent.retrieve — No LLM

- **Rationale:** Vector recall is deterministic; embedding model handles semantic similarity.
- **Phase 2 evolution:** Once episodic memory > 200 incidents, recall ceiling drops. Add `bge-reranker-v2-m3` (already loaded for RAG) on top — still no LLM. Do not introduce a "judge similarity" LLM call here.

### #3 PlannerAgent.plan — Cloud `deepseek-v4-pro`

- **Changed:** 2026-05-25, reason: DeepSeek-V3 retired upstream (API now exposes only `deepseek-v4-pro` / `deepseek-v4-flash`). `deepseek-v4-pro` is the official successor with ≥ V3 capability — an upgrade, not a downgrade, so no re-justification needed beyond this note.
- **Rationale:** Multi-fact composition, reasoning depth. V4-Flash produces over-decomposed DAGs (verified in Specialist decompose ablation; same model class behaves similarly here), so the reasoning tier (now `deepseek-v4-pro`) is required.
- **Ablate condition:** If IEQ-Bench plan-quality metric is within 2 pp of `deepseek-v4-flash`, downgrade to flash to save latency/cost.
- **Fallback:** `deepseek-v4-pro` timeout > 30 s or 5xx → retry once on `deepseek-v4-flash`. Second failure → create Tier 3 incident "Planner offline, manual triage required". Never silently drop the incident.

### #4a Specialist.decompose — Cloud V4-Flash

- **Rationale:** Needs domain term understanding to split sensibly; local 8B over-decomposes.
- **Hard cap:** Prompt enforces ≤ 3 sub-queries to prevent runaway retrieval.
- **Fallback:** API failure → degrade to single-query mode (treat entire subtask as one query), log degradation flag in trace.

### #4c Specialist.grade ★ — Cloud V4-Flash (mandatory)

- **Rationale:** Completeness judgement. A4.5 closed-book Q16/17/22/23 showed local 8B says "enough info" with high confidence even when chunks are clearly missing the answer. Cascade error: false-positive grade → no rewrite → bad generate.
- **Ablate condition:** Run IEQ-Bench against V3 (not Flash) for `grade`. If grade-recall (caught-missing-info / actually-missing) improves > 5 pp, upgrade to V3.
- **Fallback:** API failure → conservative default (always grade "insufficient" once, force one rewrite cycle). Avoids false-positive "good enough" verdicts.

### #4d Specialist.rewrite — Local Qwen3-8B (watched)

- **Rationale (caveat):** Short-string transform on surface; but rewrite must read grade feedback ("missing ASHRAE 62.1 specific value") and produce a useful new query. Local 8B is **theoretically risky** here.
- **Ablate condition (priority):** Add a dedicated IEQ-Bench subtask "rewrite quality" — measure whether the rewritten query causes the next retrieve to return the missing chunk. If hit rate < 70 %, upgrade to V4-Flash. **Default: re-check this every two weeks during Phase 2-3 buildup.** Cost delta is < ¥1/month — never resist upgrading on cost grounds.
- **Fallback:** Local 8B unavailable → cloud V4-Flash directly.

### #4e Specialist.generate ★ — Cloud V4-Flash (mandatory)

- **Rationale:** A4.5 measured **14 pp hit-only gap** here. Local 8B refuses to surface specific values present in chunks ("原文未提及" on "5 cfm/person" when it's literally in the chunk). This single node carries the IEQ-Bench score.
- **Ablate condition:** Upgrade to V3 if V4-Flash hit-only < 85 %. Never downgrade.
- **Fallback:** V4-Flash failure → V3 → Tier 3 incident.
- **Required output schema:** Must include `expected_outcome: {target_metric: str, target_value: float, target_time_min: int}`. Enforced by Pydantic at node output (Hard Constraint #13).

### #5 CriticAgent.validate — Local (Plan B: no chunk trace-back)

- **Plan B (2026-05-28, supersedes the trace-back design below):** The original plan was numeric trace-back of each claim against the cited chunks. That is **impossible** under the SpecialistSubgraph state isolation (🔴 Phase 2 risk #2): `retrieved_chunks` never enter the parent checkpoint by design, so the parent critic cannot see the source text. Decision: the critic validates only what it CAN see — (1) a **deterministic** plausibility floor on `expected_outcome` (target_metric known, target_value in a physical range, target_time_min sane — no LLM), and (2) an LLM judgement of the diagnosis's **internal coherence + outcome-to-diagnosis fit**. On disapproval the incident fails WITHOUT acting (Phase 3 will route to replan).
- **Rationale:** Both checks are within local 8B's reach — the deterministic floor needs no LLM, and the coherence judgement is a self-contained "does this paragraph contradict itself / does the outcome follow" call, not a long-context faithfulness task. No claim-type classification is needed because there is no source text to trace against. Routed LOCAL (currently `deepseek-v4-flash` — override B).
- **Fallback:** LLM unavailable → deterministic plausibility floor alone decides (approve iff no floor violation); the numeric floor still blocks unsafe actuation, so an outage degrades coverage without deadlocking the loop.
- **Ablate condition:** Track the action-on-bad-diagnosis rate on IEQ-Bench (Phase 4). If coherence false-negatives let through unsafe diagnoses, escalate the coherence call to V4-Flash. Original trace-back design (claim classification, numeric→local / inductive→Flash) is retained below only as the spec for a future variant where citations are surfaced (Plan A).
- ~~**Trace-back design (Plan A, not taken):** Classify each claim type at the front of Critic. Numeric / direct-quote claims → local. Inductive / multi-fact claims → escalate to V4-Flash. Requires `SpecialistResult.citations` to cross the isolation boundary.~~

### #6 VerifierAgent.check — Local Qwen3-8B

- **Rationale:** Pure numeric comparison + threshold against `expected_outcome` schema. Same task class as Monitor.
- **Dependency:** Only safe **because** Hard Constraint #13 forces structured `expected_outcome`. If Specialist ever emits free-text expected outcomes ("should improve"), this node must escalate to V4-Flash.
- **Fallback:** Local 8B unavailable → V4-Flash.

### #7 / #8 Reflector ★ — Cloud `deepseek-v4-pro` (mandatory)

- **Changed:** 2026-05-25, reason: DeepSeek-V3 retired upstream; `deepseek-v4-pro` is the official successor (≥ V3). The "mandatory cloud reasoning tier" guarantee is preserved — `deepseek-v4-pro`, never local, never `deepseek-v4-flash`. Pin this exact model for the dissertation's Week 8 vs Week 1 run; do not mix model versions across the 8-week window.
- **Rationale:** Multi-incident induction + causal mechanism extraction. A4.5 confirms local 8B fabricates wholesale on this task class. Quality of semantic facts and SOPs determines whether the Week 8 vs Week 1 improvement claim holds.
- **Token-size hazard:** A week of incidents can exceed 100K tokens. **Must chunk by incident type** (one Reflector call per category: AirQuality / Thermal / Lighting / Acoustic) and merge results in a final summarisation pass. Single-shot reflection will OOM V3's 128K window.
- **Output gating:** Procedural SOPs (#8) are written to a `pending_sops` queue, not directly to Procedural Memory. Human signs off before activation — a hallucinated SOP would silently corrupt all future incident handling.
- **Fallback:** `deepseek-v4-pro` failure → defer to next Sunday, alert operator. Never run on local, never silently downgrade to flash.

### #9 ConversationalAgent.respond — Cloud V4-Flash with escalation

- **Rationale:** User-facing latency budget (< 3 s first token). Streaming V4-Flash hits this. V3 would feel sluggish.
- **Escalation:** If V4-Flash self-rates confidence < 0.7 (asked in the same prompt as the answer), automatically re-issue on V3 and replace.
- **Fallback:** API failure → "I can't reach the cloud right now; here's what I found in memory: ..." with raw retrieval result. Never block on retry.

### #10 rag.ingest.contextual_prefix — Cloud V4-Flash + KV cache

- **Rationale:** Batch one-shot, Track A measured 96.4 % cache hit, ¥10-50 per full corpus pass.
- **Fallback:** No fallback needed; this is a build-time step.

### #11 eval.judge — GPT-4o + Claude Sonnet 4.6

- **Rationale:** Dual-judge for independence. Already the dissertation methodology.
- **Hard prompt constraint:** Judge prompts must include "only compare to expected, do not use prior knowledge" — otherwise judges leak world knowledge into "partial credit" decisions.

---

## Capability Profile Summary (from A4.5)

Tasks local Qwen3-8B handles reliably:

- Threshold judgement, rule matching, short-string rewrite
- Token-level comparison, JSON field extraction

Tasks local Qwen3-8B fails on:

- Reciting specific details (numbers, named entities) from long context — 14 pp gap
- Multi-element induction / causal mechanism — fabricates wholesale
- Self-reflective "is this enough info?" — confidently says yes when wrong
- Subtask decomposition — over-decomposes
- Recall-vs-context boundary — uncontrollable

Routing in this document follows these profiles. Re-run the capability profile any time a new local model version becomes available (e.g. Qwen3.5-8B, Qwen4-8B) before relaxing any "mandatory cloud" tag.

---

## Cost Envelope (monthly, single building, 10 real incidents/day)

| Node | Calls/mo | Unit cost | Monthly |
|------|----------|-----------|---------|
| #1 Monitor | 8640 | local | ¥0 |
| #3 Planner v4-pro † | 300 | ~¥0.02 | ~¥6 |
| #4a/c/e Specialist (Flash) | ~2100 | ~¥0.0015 avg | ~¥3 |
| #5/#6 Critic + Verifier | 600 | local | ¥0 |
| #7/#8 Reflector v4-pro † (chunked × 4 cats) | ~32 | ~¥0.10 | ~¥3 |
| #9 Conversational | ~200 | ~¥0.002 | ~¥0.5 |
| #10 Ingestion | one-shot | — | ~¥50/full pass |
| #11 Dual judge | ~20 × 200 | ~¥0.50/task | ~¥50 |
| **Running monthly** | | | **~¥65** |

4-week autonomous run budget: ≈ ¥80 ops + ¥50 ingestion = **¥130 total LLM spend**. Inside dissertation budget.

> † Unit costs for `#3`/`#7`/`#8` are carried over from the retired DeepSeek-V3 pricing. `deepseek-v4-pro` is a Pro-tier reasoning model and likely prices higher — **re-confirm against DeepSeek's current price list before quoting these numbers in the dissertation.** Low call volume (≤ 300/mo + 32/mo) keeps the absolute impact small regardless.

---

## How to Use This File

- **Adding a new node:** Add a row to the 11-call-points table + a Rationale section. Update `core/router.py`. Cite the capability evidence (A4.5 question ID, or new ablation).
- **Changing a node's model:** Bump the row, add a `Changed: YYYY-MM-DD, reason: …` line in the Rationale section. Re-run IEQ-Bench and attach the delta in the PR description.
- **Disagreeing with a "mandatory cloud" tag:** Read the corresponding Hard Constraint in `CLAUDE.md` first. If you still want to challenge, run the equivalent of the A4.5 question battery on the candidate local model and post the numbers. Do not relax the tag based on cost alone.
