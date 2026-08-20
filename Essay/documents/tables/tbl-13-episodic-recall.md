**Table 13. Episodic memory recall@k — the REAL embedding search, not a hand-fed case (T2.3).**
For each of the 12 L3 recurrence tasks, all 12 seeded episodes are embedded into a throwaway Qdrant collection using the exact same asymmetric anomaly-signature encoding as `memory/episodic.py` (`_anomaly_text(sensor, value, rule_violated)`). The task's NEW anomaly (same mechanism, different room/value from its own seeded episode) is then embedded and queried against the full 12-episode pool — a genuine 12-way disambiguation, not the memory-ablation harness's hand-injected "correct" case.
Source: `eval/reports/episodic-recall-20260818T072850Z.json`; `ops/scripts/episodic_recall_experiment.py`.

| Task | Domain | Rank of correct episode | Top-1 recalled | Confused with |
|---|---|:--:|---|---|
| co2-damper | airquality | 3 | co2-dcv | co2-dcv |
| co2-allhands | airquality | 2 | co2-damper | co2-damper |
| co2-damper-R3 | airquality | 3 | co2-dcv | co2-dcv |
| co2-dcv | airquality | 2 | co2-damper-R3 | co2-damper-R3 |
| thermal-solar | thermal | 1 | (self) | — |
| thermal-solar-east | thermal | 1 | (self) | — |
| thermal-reheat | thermal | 2 | thermal-solar-east | thermal-solar-east |
| lighting-blind | lighting | 1 | (self) | — |
| lighting-lamp | lighting | 1 | (self) | — |
| acoustic-fan | acoustic | 1 | (self) | — |
| acoustic-fan-bearing | acoustic | 1 | (self) | — |
| acoustic-partition | acoustic | 2 | acoustic-fan-bearing | acoustic-fan-bearing |

| Metric | Value |
|---|:--:|
| **macro recall@1** | **0.50** (6/12) |
| **macro recall@3** | **1.00** (12/12) |
| macro MRR | 0.722 |
| within-domain confusions | 6/12 |

**Reading:** raw embedding-based recall is imperfect at rank 1 — half the time the nearest historical case by anomaly signature is a *different* past incident in the *same* domain (e.g. a `co2-damper` anomaly first recalls `co2-dcv`), because the asymmetric encoding is anchored on the anomaly alone (sensor + rule + value), which is the only thing known at planning time, not the eventual cause. But recall@3 is a clean 1.00 across all 12 tasks — the correct case is *always* in the top-3. This is not a coincidence: `memory/episodic.py.DEFAULT_TOP_K = 3` is exactly the production setting, and this result is the first direct evidence that that choice is load-bearing — at `top_k=1` the planner would see the wrong precedent on half of these recurring incidents.
**Limitations:** n=12, one throwaway collection, four domains with 2–4 episodes each (not a large-scale confusion study); a real deployment's episodic store will grow and could dilute recall@3 further — this result bounds the *current* library size, not an asymptotic guarantee.
