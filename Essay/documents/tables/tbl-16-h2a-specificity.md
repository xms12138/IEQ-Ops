**Table 16. H2a specificity — does memory over-trust an irrelevant precedent? (T2.2)**
Four novel anomalies, one per domain, each with a plausible root cause that is **not** any of the 12 seeded recurrence episodes. The real embedding-based retrieval (same throwaway pool as Table 13) recalls the top-3 nearest past cases by anomaly signature; the planner and specialist run once with that recall and once without, on the identical anomaly.
Source: `eval/reports/h2a-specificity-20260818T084041Z.json`; `ops/scripts/h2a_specificity_experiment.py`.

| Novel anomaly | True (intended) cause | Recalled (irrelevant) cases | Diagnosis WITHOUT memory | Diagnosis WITH memory |
|---|---|---|---|---|
| CO2 1150 ppm, low occupancy | windows sealed shut | co2-damper, co2-allhands, co2-damper-R3 | "inadequate ventilation" (generic, safe) | **"a stuck or jammed outdoor-air damper"** (specific, wrong, borrowed) |
| Temp 26.5°C, night setback | HVAC night-setback failed to reset | thermal-solar-east, thermal-solar, thermal-reheat | "adjust HVAC to cool the space" (generic, safe) | **"solar gain through unshaded east/west glazing"** (specific, wrong, borrowed) |
| Lux 240, sensor miscalibration | daylight sensor over-dimming | lighting-blind, lighting-lamp, thermal-solar-east | "insufficient electric lighting output" (generic, safe) | **"stuck motorised blinds... and aged LED depreciation"** (two wrong causes, blended from two recalled cases) |
| Noise 52 dBA, door propped open | corridor fire door | acoustic-fan, acoustic-partition, acoustic-fan-bearing | "HVAC equipment or exterior noise intrusion" (generic) | **"HVAC supply fan imbalance"** (specific, wrong, borrowed) |

| Metric | Value |
|---|:--:|
| **Contamination rate** | **1.00 (4/4)** |

**Reading — a genuine, important negative result, not a methodology artifact.** In every case, injecting memory did not add a caveat alongside a sound generic diagnosis — it **replaced** the generic-but-defensible diagnosis (which the no-memory arm reached correctly, grounded in the corpus and the current reading) with a **specific, confidently-stated, wrong cause borrowed from the nearest historical precedent**, even though that precedent's true cause has nothing to do with the current anomaly. This is the direct precision cost of the same mechanism Table 15 credits for a +1.00 recall lift: the planner's v4 prompt explicitly instructs carrying a recalled cause into the primary goal, and the specialist's `generate` node does not independently verify the recalled cause against the current anomaly's actual context before adopting it — there is currently no relevance gate between "a case was recalled" and "its cause is trusted."

**This qualifies, but does not reverse, Table 15's recall-lift result.** The system genuinely improves on RECURRING incidents (the mechanism Tables 5/13/15 measure) but at a real, now-quantified cost on NOVEL incidents that merely resemble a past one by sensor/domain — a precision-recall trade-off inherent to the current asymmetric-embedding design (memory/episodic.py), not a bug in one component. Flagged as a priority item for Future Work: gate memory injection on a similarity or corroborating-evidence threshold rather than always injecting the top-k recall.

**Honest limitations:** n=4 (one per domain — a first probe, not a large-scale precision study); the four novel anomalies were hand-authored by the author to plausibly differ from every seeded cause, which is itself a judgement call; contamination is measured by literal keyword presence (matching Tables 5/15's method), so a diagnosis that mentions a recalled term only to explicitly rule it out would still count as "contaminated" — none of the four diagnoses above did this (all state the wrong cause as the likely explanation), but the metric does not distinguish the two.
