**Table 11. Node-level LLM routing validation.**
Each safety-critical node has a measured capability metric and an escalation trigger; under the current cloud-flash configuration all nodes clear their threshold, so none escalate.
Source: `eval/reports/ablate-check-20260531T233809Z.json`; `ops/llm_routing.md`.

| Node | Metric | Trigger | Measured | n | Escalate? |
|---|---|---|---|---|---|
| `specialist.grade` | error_rate | > 0.15 | **0.0** | 6 | No |
| `specialist.generate` | hit_only | < 0.85 | **1.0** | 2 | No |
| `specialist.rewrite` | gold_mrr_after | < 0.70 | **1.0** | 2 | No |
| `critic.validate` | error_rate | > 0.15 | **0.0** | 5 | No |
| `planner.plan` | dag_validity | < 0.90 | **1.0** | 5 | No |

**Capability floors (A4.5):** local Qwen3-8B is reliable for threshold judgement, rule matching, short-string rewrite, token-level comparison and JSON extraction, but fails on faithful recall of specific values from long context (14 pp hit-only gap), multi-fact induction/causal reasoning, and self-reflective sufficiency judgement — hence `grade`/`generate`/reflection are pinned to cloud.
**Cost envelope:** ≈ ¥65 / month for a single building at 10 incidents/day; the dual-judge evaluation (≈¥50) is an evaluation-only cost, removable in production.
