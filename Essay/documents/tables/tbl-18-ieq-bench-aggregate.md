**Table 18. IEQ-Bench aggregate — an across-capability rollup that no single prior report had assembled (T3.2).**
Combines a fresh `--seed` run (L1 retrieval + L2 grade/rewrite/generate/critic/planner, every REAL system entry, n=6-10 samples for stochastic capabilities), a fresh `--compare` L3 e2e run (system arm only; the ReAct baseline comparison stays Table 12's job), and the diagnosis-level L3 recurrence result (Table 15, memory ON — production always has recall available).
Source: `eval/reports/ieq-bench-aggregate-20260818T100915Z.json`, `eval/reports/seed-20260818T101036Z.json`.

| Layer | Capability | n | Pass rate |
|---|---|:--:|:--:|
| L1 | retrieval | 5 | 1.00 |
| L2 | critic | 5 | 1.00 |
| L2 | generate | 2 | 1.00 |
| L2 | grade | 6 | 0.833 |
| L2 | planner | 4 | 1.00 |
| L2 | **rewrite** | 2 | **0.00** (see below — stale fixture, not a capability failure) |
| L3 | e2e (system arm) | 6 | 0.833 |
| L3 | recurrence (diagnosis, memory ON) | 12 | 1.00 |

| Metric | Value |
|---|:--:|
| **Overall, as measured** | **38/42 = 90.5%** |
| **Overall, excluding the 2 known-stale rewrite fixtures** | **38/40 = 95.0%** |
| **Capability-plane only, excluding recurrence (L1+L2+L3-e2e)** | **26/30 = 86.7%** |
| **Recurrence alone (L3, diagnosis, memory ON)** | **12/12 = 100%** |

**Why recurrence is broken out separately instead of folded into one headline number.** The 12/12 recurrence rows are Table 15's result, and Table 15 itself is explicit that this figure is *process fidelity, not ground-truth diagnostic correctness* — the recalled cause is definitionally present in the episode fed to the planner, so a working recall pipeline naming it back is close to a consistency check, not an independent test of skill (Table 5's "Reading" section calls the same 0→1.00 shape "partly built in by design"). Table 16 then shows the identical mechanism produces a 100% *contamination* rate on novel, non-recurring anomalies. Averaging a metric that is partly-by-construction with genuinely-uncertain capability probes (L2 grade 0.833, L3 e2e 0.833) into one 90.5% would let the easiest number quietly do the most work. The capability-plane figure (26/30 = 86.7%, no recurrence rows) is the fairer single number for "how good is this system at things that could plausibly go wrong"; 90.5%/95.0% are reported alongside it for completeness, not as the preferred headline.

**The L2 rewrite 0.00 is a disclosed test-fixture bug, not a regression in the rewrite node.** Both `L2-rewrite-co2-ops` and `L2-rewrite-thermal-comfort` declare `gold_sources: ["ops-note"]` and `["ashrae-55"]` respectively — source identifiers from the multi-source placeholder corpus this project used before consolidating to a single free WELL v2 PDF (Table 10 / `project_corpus_source`). Every chunk in the live corpus now has `source = "well-v2"`; neither "ops-note" nor "ashrae-55" can ever match, so `mrr_after` is mechanically 0.0 regardless of how good the rewritten query is — confirmed directly: `mrr_before = mrr_after = 0.0` for both tasks, and the task files' own authoring notes record a real historical measurement ("弱query排第5, MRR 0.2" / "排第3, MRR 0.333") from before the corpus changed. This is disclosed as unresolved test debt, not silently patched or excluded from any of the numbers above (Future Work: migrate `l2_rewrite.jsonl`'s gold from `gold_sources` to `gold_chunk_idx`, the same granularity fix Table 14 already needed for the post-consolidation corpus).

**Reading:** on the capability-plane number (86.7%), L2 grade (0.833) and L3 e2e (0.833) are the two genuinely imperfect-but-real results, both small-n (n=6) with individual task failures auditable in the linked reports rather than papered over. These figures are reported as one aggregate snapshot, not measured against a project-internal pass/fail bar — the reader can weigh 86.7% against whatever standard they consider appropriate for a small, deterministic-and-LLM-judged probe suite.

**Honest limitations:** n is still modest per capability (L1/L2 draw from IEQ-Bench's existing seed task files, not a full 200-task v1 set); the L3 e2e run used n=5 samples/task for cost reasons; this is a snapshot aggregate, not a tracked-over-time benchmark run; the recurrence/capability split above is itself a judgement call about which metrics are commensurable, made transparent rather than resolved by picking one number.
