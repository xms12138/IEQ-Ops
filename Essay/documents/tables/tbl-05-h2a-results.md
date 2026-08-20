**Table 5. H2a — episodic memory recall ablation (L3 recurrence, n = 12).**
For each recurrence task the *same* planner (temperature 0) is run twice on the *same* new anomaly: once with an empty recall (memory OFF) and once with the seeded past `EpisodicCase` (memory ON). The metric is whether the building-specific cause/fix — knowledge that is **not** in the standards corpus — surfaces in the plan's subtask goals.
Source: `eval/reports/ablate-memory-20260818T023543Z.json`.

| Domain | Tasks | Cause cue (recall_gold) | Macro-lift |
|---|---|---|:--:|
| airquality | co2-damper, co2-damper-**R3**, co2-dcv, co2-allhands | damper / sensor drift / pre-empt | +1.00 |
| thermal | thermal-solar, thermal-solar-**east**, thermal-reheat | solar / reheat valve | +1.00 |
| lighting | lighting-blind, lighting-lamp | blind / lamp replace | +1.00 |
| acoustic | acoustic-fan, acoustic-fan-**bearing**, acoustic-partition | fan / bearing / partition | +1.00 |
| **All (n=12)** | | | **+1.00** (OFF 0.00 → ON 1.00) |

**Reading (scope carefully):** this is a **planning-level recall demonstration, not a diagnosis-accuracy result**. With memory off the planner produces a generic diagnostic goal; with recall on it injects the specific past cause (Fig. 14). The perfect column (0.00 → 1.00) is **partly built in by design** — the cause is present in the recalled episode, so a well-behaved planner echoing it in the goal is expected — so the number is best read as a consistency check, not a headline score. What the experiment *does* add is **breadth across contexts**: the cause transfers across four domains (lighting added this round) and across **mechanism-level variations** — `co2-damper-R3` (same stuck-damper cause, different room and severity), `thermal-solar-east` (east/morning vs west/afternoon), `acoustic-fan-bearing` (bearing-wear vs imbalance) — where the new anomaly differs from the seeded episode in room, value and confounders, so the prior *generalises* rather than matching an identical task.

**Limitations (stated honestly):** the metric is *plan-level recall*, not final diagnosis correctness — indeed one archived case (`co2-damper`) is still scored `missed` with memory on, so a sharpened goal does not guarantee a right answer. Not tested here: end-to-end diagnosis accuracy (running the full specialist against the gold cause), specificity on non-recurring events, and the longitudinal "improves-over-time" claim (H2b, deferred). n = 12 is small. This result should therefore be cited as *mechanism evidence that recall focuses the plan*, in line with its original framing in the evidence inventory.
