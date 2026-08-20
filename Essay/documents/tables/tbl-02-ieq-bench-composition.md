**Table 2. IEQ-Bench composition (v0).**
The benchmark is organised by layer: L1 tests retrieval, L2 tests individual agent-node capabilities in isolation, L3 tests end-to-end incident handling. Ground truth comes from the WELL v2 corpus (retrieval/answer tasks) and the physics simulator's known root cause (recurrence/e2e tasks).
Source: `eval/ieq_bench/tasks/*.jsonl`.

| Layer | Task file | Capability tested | n |
|---|---|---|:--:|
| L1 | `l1_retrieval` | standards retrieval | 6 |
| L2 | `l2_planner` | subtask-DAG planning | 5 |
| L2 | `l2_grade` | self-reflective sufficiency | 11 |
| L2 | `l2_generate` | grounded synthesis | 3 |
| L2 | `l2_critic` | diagnosis plausibility | 6 |
| L2 | `l2_rewrite` | query rewrite | 9 |
| L3 | `l3_e2e` | end-to-end incident | 8 |
| L3 | `l3_e2e_hard` | hard / adversarial e2e | 13 |
| L3 | `l3_recurrence` | memory-recall (H2a) | 10 |
| | | **Total** | **71** |

**Honest note:** this is a v0 of the planned 200-task benchmark; at 71 tasks with many saturating at 1.00 on a strong base model, aggregate pass-rate has low discriminative power (see Table 12). The discriminative signal comes from the *targeted* ablations — grounding (Table 4), memory recall (Table 5), and the `generate` node's instability in weak-evidence domains — not from an overall score. Expanding L1/L3 with RAG-discriminative items (Table 4 method) is the priority hardening step.
