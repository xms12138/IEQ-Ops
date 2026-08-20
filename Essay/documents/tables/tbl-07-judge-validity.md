**Table 7. Judge validity — inter-judge agreement and judge-vs-deterministic-grader agreement (T2.4).**
74 real (candidate, expected) pairs from the H1 closed-book + RAG runs (Table 4) — every candidate answer the system actually produced this round, not a synthetic set — independently scored by two judges from **different model families**: `deepseek-v4-flash` (the judge used implicitly throughout, via `eval/judge.py`) and Alibaba DashScope's `qwen-plus` (a separate provider, separate weights). Both are compared against the deterministic grader (`closedbook_prescreen.grade()`) already used for every H1 number in this dissertation.
Source: `eval/reports/judge-validity-20260818T075649Z.json`; `ops/scripts/judge_validity_experiment.py`.

| Comparison | Agreement | Cohen's kappa | Interpretation |
|---|:--:|:--:|---|
| deepseek-judge vs qwen-judge (inter-judge) | **0.919** | **0.822** | almost perfect |
| deepseek-judge vs deterministic grader | 0.892 | 0.771 | substantial |
| qwen-judge vs deterministic grader | 0.865 | 0.714 | substantial |

**Reading:** two independently-weighted judge model families agree with each other on 92% of items (kappa 0.82, "almost perfect" on the standard Landis & Koch scale), and both agree with the deterministic grader used throughout H1/H2a at a "substantial" level (kappa 0.71–0.77). This is evidence *for* the deterministic grader's reliability, not just a judge-vs-judge check: if grounded LLM opinion routinely disagreed with the string-matching grader, every H1 number in this dissertation would be suspect. It does not — the small residual disagreement (6–10 items out of 74) concentrates on exactly the near-duplicate-table and full-row-quoting cases already flagged qualitatively in Table 4 (e.g. `noise-well`, `pm25-enhanced`, `formaldehyde-enhanced`), where a human reading the full answer text would also find the "correct" label genuinely debatable.

**Scope decision (honest, not fabricated):** a true judge-vs-**human** validity check needs the author's own annotation of a held-out sample, which was out of scope for this automated pass — a Claude Code agent scoring its own judge comparison cannot stand in for a human rater. This is recorded as future work, not approximated.
