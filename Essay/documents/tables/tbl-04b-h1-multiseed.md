**Table 4b. H1 multi-seed stability — does the headline lift survive re-asking the same question? (T1.4)**
Closed-book and RAG re-run twice each (temperature 0, but the cloud reasoning model is not strictly deterministic — Table 4's disclosed caveat). Majority-vote across the 2 seeds is compared against the deterministic grader, same as every other H1 number.
Source: `eval/reports/h1-multiseed-20260818T091145Z.json`; `ops/scripts/h1_multiseed_experiment.py`.

| Metric | Seed 1 | Seed 2 | Majority-vote |
|---|:--:|:--:|:--:|
| Closed-book accuracy | 0.405 | 0.405 | 0.486 |
| RAG accuracy | 0.730 | 0.784 | 0.811 |
| Lift | — | — | **+32.5 pp** |

| Metric | Value |
|---|:--:|
| Questions with an unstable closed-book grade across seeds | 6/37 (16%) |
| Questions with an unstable RAG grade across seeds | 4/37 (11%) |
| McNemar exact p (majority-vote) | **0.0118** |

**Reading:** per-seed accuracy is close to identical for closed-book (0.405 both times — a coincidental wash: different individual questions flip 0→1 and 1→0, but the count nets out) and moves only ~5 pp for RAG between seeds. Roughly one in six closed-book questions and one in nine RAG questions genuinely flip grade on a bare re-ask at temperature 0 — quantifying, rather than just asserting, the cloud reasoning model's known non-determinism. Despite that per-item noise, the AGGREGATE finding is robust: majority-vote lift is +32.5 pp (versus the canonical single run's +32 pp, Table 4) and remains significant (p = 0.012, versus the canonical run's p = 0.0075) — the headline H1 result does not depend on having asked at a lucky moment.
