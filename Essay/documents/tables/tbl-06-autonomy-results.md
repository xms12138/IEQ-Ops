**Table 6. H3 — proactive monitoring vs. a reactive query-only assistant (detection model).**
Discrete-event simulation: 400 IEQ events over 14 days across 6 rooms, each lasting 20–120 min. The proactive Monitor scans every room every 5 min; the reactive manager checks 2 rooms per query during work hours (08–18 h) at the stated period. Seeded (rng=42), no LLM.
Source: `eval/reports/autonomy-*.json`; `ops/scripts/autonomy_experiment.py`.

| System | Detection coverage | Median lead-time | Note |
|---|:--:|:--:|---|
| **Proactive Monitor** (5-min scan, all rooms) | **1.00** | **3 min** | catches every event within one scan |
| Reactive, 0.5 h checks | 0.33 | — | aggressive polling still misses 2/3 |
| Reactive, 1 h checks | 0.14 | — | |
| **Reactive, 2 h checks** (representative) | **0.10** | **49 min** | a plausible manager cadence |
| Reactive, 4 h checks | 0.05 | — | |
| Reactive, 8 h checks | 0.04 | — | |

**Scope — this is a scheduling model, not a test of the LLM system.** It contains no LLM and no IEQ content (proactive detection is simply the first scan after onset); it quantifies an *upper bound* on what continuous polling buys over intermittent human checking, and motivates the autonomous loop rather than validating the system's reasoning.
**Reading — lead with lead-time, not coverage.** Even for events a reactive manager would *eventually* catch, proactive detection leads by a median **3 vs 49 minutes** — a fair, low-strawman comparison. The coverage gap (1.00 vs 0.10) is larger but partly reflects a **conservative reactive baseline** (2 of 6 rooms, work-hours only), so it is reported as a *bound*: the sweep (Fig. 15) shows reactive coverage never approaches the proactive line, which follows structurally from one person not being able to watch every room continuously.
**Assumptions (stated honestly):** coverage and lead-time depend on event duration and the reactive query budget, both deliberately conservative modelling choices; the direction (proactive detects sooner and more completely) is robust across the swept range, but the absolute reactive numbers would shift with different assumptions and are not a like-for-like measurement of this system.
