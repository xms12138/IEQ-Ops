**Table 4. H1 — grounding ablation on the RAG-discriminative question set (n = 37, hardened 2026-08-18).**
Same base model (`deepseek-v4-flash`, temperature 0) and same deterministic grader; the only change is whether retrieved WELL v2 excerpts are supplied. Question set expanded 17→37 across all four domains (airquality 22, lighting 6, thermal 5, acoustic 4 — airquality's share reflects its larger page-count in the corpus, stated honestly rather than artificially balanced); every item that could be tiered by achievement-level or space-type now names its tier explicitly (§ methodology note in `ops/scripts/closedbook_prescreen.py`). Grader hardened with word-boundary matching after a false-positive was caught (a CAS registry number "71-43-2" was matching the myth token "3"). Closed-book = the pre-screen; RAG = grounded in top-5 retrieved chunks (BGE-M3 + reranker over 824 corpus chunks).
Source: `eval/reports/closedbook-prescreen-20260818T074637Z.json`, `eval/reports/h1-rag-ablation-20260818T075118Z.json`.

| Metric | Value |
|---|---|
| Closed-book (No-RAG) grounded accuracy | **0.43** (16/37) |
| RAG grounded accuracy | **0.76** (28/37) |
| Absolute lift | **+32 pp** |
| Discordant pairs (RAG better : worse) | 15 : 3 |
| McNemar exact two-sided p | **0.0075** |

**Reading:** at n = 37 the lift is +32 pp, closely matching the original n = 17 pilot's +35 pp, and this time the discordant-pair test is **significant** (p = 0.0075, not the earlier underpowered p = 0.11) — the larger, tier-disambiguated question set turns the same direction of effect into a result that clears a conventional significance threshold. Retrieval recovers 15 of the 19 items the closed-book base got wrong (e.g. CO₂ 900 ppm, PM2.5/PM10, several thermal zone/velocity facts, four of the six Enhanced-tier inorganic-gas values), while only 3 items regress.

**Three regressions, each explicable — not random noise:**
- `ashrae-myth` — the corpus is WELL-only; grounding correctly declines to answer an ASHRAE-specific claim ("not in the provided excerpts"), while the ungrounded base happened to know the general concept from pretraining. A correct "I don't have this" is scored wrong by a grader that only checks for the expected claim — a grading-scope artifact, not a grounding failure.
- `pm25-enhanced`, `benzene-enhanced` — both are **base-vs-Enhanced near-duplicate table confusions**: the corpus contains two structurally similar tables (e.g. base VOC test benzene = 10 µg/m³ vs the Enhanced Organic Gases feature benzene = 3 µg/m³) a few pages apart, and even though the question explicitly names the tier ("Enhanced… not the base A04 test"), the retrieved/generated answer still surfaces the neighbouring table's value. This is the most important qualitative finding this round: **explicit tier-naming in the prompt does not guarantee correct disambiguation when the corpus itself contains near-duplicate content** — grounding here is worse than useless, it supplies a confident, wrong, on-topic number.

**Six items still wrong under both conditions** (`noise-well`, `pm10-enhanced`, `formaldehyde-enhanced`, `lighting-glare-2pt`, `acoustic-lmax-cat3`, `acoustic-cat3-dbc-1pt`) are the hard core of the same phenomenon: `noise-well`'s RAG answer is graded a myth-hit because it quotes the *entire* tier row (correctly identifying 50 dBA as Category 3, but also naming the neighbouring Category 2/1 values in the same row) — a grader-strictness artifact, not a wrong answer; `pm10-enhanced`/`formaldehyde-enhanced` reveal the Enhanced tables have **their own internal 1-point/2-point sub-tiers** (e.g. Enhanced PM2.5 is 12 µg/m³ at 1-point, 10 at 2-point) that this round's questions did not anticipate — the corpus's tiering goes at least two levels deep in places.

**Honest limitations:**
- **Single run, temperature 0 still not fully deterministic** — a separate multi-seed check (`ops/scripts/h1_multiseed_experiment.py`, Table 4b) repeats a subset of questions to quantify run-to-run flip rate.
- **Grader is context-blind, not just keyword-blind** — it cannot tell "the answer correctly cites 50 dBA and ALSO transparently quotes the neighbouring category values" from "the answer wrongly asserts the neighbouring category's value as the answer." Both `noise-well`-style false negatives and the CAS-number false positive (now fixed) stem from the same root cause: literal substring matching has no notion of which number is being *asserted as the answer* versus *cited as context*.
- **Domain balance reflects the corpus, not a stratified design** — airquality is 22/37 (59%) because the WELL v2 Air section is the largest (36 pp vs ~25 pp for the other three concepts combined); this is disclosed rather than corrected by discarding valid items.
