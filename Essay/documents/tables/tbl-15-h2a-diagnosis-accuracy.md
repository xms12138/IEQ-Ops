**Table 15. H2a end-to-end diagnosis accuracy — does the memory lift survive to the final diagnosis TEXT? (T2.1)**
Strictly deeper than Table 5's plan-level check: for each of the 12 recurrence tasks, the planner (recall OFF vs ON) produces a plan, the primary subtask's goal is run through the REAL `SpecialistSubgraph` (decompose → retrieve → grade → rewrite → generate against the live WELL v2 corpus), and the resulting diagnosis TEXT — not just the plan's subtask goal — is checked for the recalled building-specific cause.
Source: `eval/reports/h2a-diagnosis-accuracy-20260818T083444Z.json`; `ops/scripts/h2a_diagnosis_accuracy.py`.

| Metric | Value |
|---|:--:|
| Diagnosis hit rate, memory OFF | **0.00** (0/12) |
| Diagnosis hit rate, memory ON | **1.00** (12/12) |
| Macro lift | **+1.00** |

**Reading:** with memory off, the specialist has no way to know the building-specific historical cause — it correctly grounds the diagnosis to the standards corpus and the current reading, but cannot name a cause the corpus itself doesn't contain (e.g. "the CO2 damper is stuck" is not a WELL v2 fact). With memory on, the recalled cause surfaces in 100% of final diagnoses across all four domains — the plan-level lift (Table 5) is not diluted by the specialist's independent retrieval-and-generation step; it fully propagates end to end.

**Methodological correction made during this run:** the first pass scored 11/12 (missing `acoustic-fan`) using an AND-of-all-synonyms check inherited from `eval/metrics.score_generate_hit`. Inspection showed the diagnosis text correctly said *"the unbalanced HVAC supply fan"* and *"rebalance the HVAC supply fan at the source"* — it never used the literal string "imbalanc" from the four-synonym gold set `['fan','imbalanc','unbalanc','rebalanc']`, which was authored for `ablate_memory`'s **any**-of-gold plan-level check, not an **all**-of-gold check. Rescoring with the correct OR semantics (matching the plan-level check's own design) yields the clean 12/12 above. This is disclosed as a scoring-semantics bug found and fixed, not a result adjusted after the fact to look better — the raw off=0.0 side is identical in both passes; only the acoustic-fan on-side verdict changed.

**Honest limitations:** n=12, single run (specialist generate/rewrite nodes sample at temperature>0, so a rerun could vary slightly); this measures whether the recalled cause is *named*, not whether it is the objectively best explanation of the anomaly (a domain expert would still need to confirm a stuck damper against physical evidence) — it is process fidelity (does the retrieved memory make it into the answer), not ground-truth diagnostic correctness against an independent oracle.
