# Evaluation results

Raw output of the evaluation runs referenced in the dissertation. These are
**data, not code** — each file is a JSON dump produced by scoring the system
(and, where relevant, a ReAct baseline) against `eval/ieq_bench/tasks/*.jsonl`
with the harness in `eval/runner.py` / `eval/judge.py` / `eval/metrics.py`.

Every number below is measured, not illustrative. Numbers in parentheses are
sample sizes — most runs are small (this is a single-deployment case study,
not a large-N study), so read them as directional evidence, not
tight confidence intervals.

| File | What it measures | Headline result |
|---|---|---|
| `ieq-bench-aggregate.json` | IEQ-Bench v1 overall score, rolled up across L1 (retrieval), L2 (per-node capability), L3 (end-to-end + recurrence) | **90.5 % overall pass rate** (n=42; target was ≥ 75 %) |
| `ieq-bench-seed-16way.json` | Stability check: same 16-task seed set re-run to check the benchmark isn't noise-dominated | see `l1_l2` breakdown in the aggregate file for the capability-level detail |
| `react-baseline-compare.json` | System vs. a single-shot ReAct baseline on the same end-to-end tasks | per-domain gap in percentage points (`gap_pp`); see caveats below |
| `e2e-closed-loop.json` | Full incident loop (monitor → plan → diagnose → critic → autonomy gate → act → verify) run to completion, including the autonomy tiering | Tier-1 auto-resolve rate **100 %** (n=8 airquality runs); Tier-3 correctly gated with **zero autonomous action** (n=9) |
| `memory-ablation.json` | Episodic memory on vs. off, same incidents | isolates what recall of past cases contributes to the plan/diagnosis |
| `routing-ablate-check.json` | Sanity check that the per-node LLM routing table (`ops/llm_routing.md`) actually changes behaviour when triggered, not just on paper | routing triggers are measurable and above floor |
| `closedbook-prescreen.json` | Closed-book (no retrieval) LLM accuracy on the IEQ-Bench QA set, used to screen for questions the base model already knows | establishes the closed-book floor that `h1-rag-grounding-*` compares against |
| `h1-rag-grounding-multiseed.json` | **H1** — does grounding in the retrieved standards corpus improve answer accuracy over closed-book, and is it stable across seeds? | closed-book majority accuracy **48.6 %** → RAG-grounded **81.1 %** (n=37 questions × 2 seeds); McNemar's test **p = 0.012** |
| `h1-rag-grounding-ablation.json` | H1 at the single-response level (no majority vote) | 43.2 % → 75.7 % |
| `h2a-episodic-diagnosis-accuracy.json` | **H2a** — does recalling a similar past incident change whether the root cause named in the diagnosis is correct, on recurring-pattern tasks? | **0 % → 100 %** diagnosis accuracy with memory recall on (n=12); macro lift = 1.0 |
| `h2a-episodic-recall-quality.json` | How good is the episodic retrieval itself (is the right past incident actually the top hit)? | macro Recall@1 = 0.50, Recall@3 = 1.00, MRR = 0.72 (n=12) |
| `h2a-episodic-recall-specificity.json` | Negative control: does the memory system falsely recall a *similar-looking but wrong* past incident for a genuinely novel case? | on 4 adversarial novel incidents sharing surface keywords with past cases, **contamination rate 100 %** — an honest limitation, not a hidden one (see dissertation discussion) |
| `h3-proactive-vs-reactive.json` | **H3** — proactive 5-minute monitoring vs. simulated reactive/on-demand polling at several periods | proactive coverage **100 %** (median lead 3 min) vs. 2-hourly reactive polling coverage **9.75 %** (median lead 49 min); full sweep across 30/60/120/240/480-minute periods included |
| `judge-validity.json` | Is the dual LLM-judge (DeepSeek-V4-Flash + Qwen3-8B) a trustworthy stand-in for a deterministic ground truth grader? | inter-judge agreement **91.9 %** (κ = 0.822); each judge vs. deterministic grader ≥ 86.5 % agreement (κ ≥ 0.71) |

## Caveats (stated plainly, not buried)

- **Baseline comparison is not uniformly favourable.** In `react-baseline-compare.json` / the `l3_e2e` block of the aggregate, the acoustic domain shows a **negative** gap (-20 pp) against the ReAct baseline on a small sample (n=5) — reported as a negative control rather than smoothed over.
- **Sample sizes are small.** This is a single research deployment evaluated against a purpose-built 42–74-item benchmark, not a large-scale study. Treat percentages as point estimates from a small n, and see the McNemar / kappa values where reported for the statistical caveats that come with that.
- **Human validity of the LLM-judge is future work.** `judge-validity.json` cross-checks two LLM judges against each other and against a deterministic grader on the questions where one exists; it does not establish agreement with a human rater (`"human_validity": "not measured — future work"` in the file itself).
