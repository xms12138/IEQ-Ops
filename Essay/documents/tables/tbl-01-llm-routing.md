**Table 1. Node-level LLM routing.**
Model selection is per LangGraph node (not per agent): local-capable nodes (threshold judgement, JSON extraction, token comparison, short rewrite) target a local Qwen3-8B; nodes needing multi-fact induction, faithfulness or causal reasoning are pinned to cloud. ★ = capability-critical, cloud mandatory.
Source: `ops/llm_routing.md`. (In the current dev configuration the "local" nodes run on `deepseek-v4-flash` — override B — pending a local Qwen deployment; cloud reasoning uses `deepseek-v4-pro`, the project's V3 replacement.)

| # | Node | Trigger | Model (design) | Why |
|---|---|---|---|---|
| 1 | `MonitorAgent.scan` | every 5 min | **local** Qwen3-8B | threshold judgement, schema-locked output |
| 3 | `PlannerAgent.plan` | per incident | **cloud** v4-pro | subtask-DAG reasoning |
| 4a | `Specialist.decompose` | per subtask | **cloud** v4-flash | query decomposition |
| 4b | `Specialist.retrieve` | per sub-query | *no LLM* | deterministic RAG call |
| 4c | `Specialist.grade` ★ | per sub-query | **cloud** v4-flash | self-reflective sufficiency |
| 4d | `Specialist.rewrite` | per failed grade | **local** Qwen3-8B | short-string transform |
| 4e | `Specialist.generate` ★ | per subtask | **cloud** v4-flash | grounded synthesis |
| 5 | `CriticAgent.validate` | per answer | **local** Qwen3-8B | plausibility floor + coherence |
| 6 | `VerifierAgent.check` | post-action | **local** Qwen3-8B | numeric schema comparison |
| 7 | `Reflector.semantic` ★ | weekly | **cloud** v4-pro | multi-incident induction |
| 8 | `Reflector.procedural` ★ | weekly | **cloud** v4-pro | SOP synthesis (human sign-off) |
| 9 | `ConversationalAgent.respond` | on-demand | **cloud** v4-flash | streaming Q&A, escalates on low confidence |
| 10 | `rag.ingest.contextual_prefix` | per corpus update | **cloud** v4-flash | contextual-retrieval prefix |

Validation of the four ★/local escalation triggers is in Table 11; the cost envelope is ≈ ¥65 / month for a single building.
