**Table 10. Standards thresholds: common belief / placeholder vs. the grounded WELL v2 value.**
These are the seed items for the H1 grounding benchmark — cases where an ungrounded model (or common practice) is wrong, so grounding is *required*, not merely helpful.
Source: DEVLOG P-013/P-014/P-016/P-019; `rag/corpus_manifest.json`; `sensing/thresholds.py`.

| Metric | Common belief / placeholder | Grounded value (WELL v2) | Clause |
|---|---|---|---|
| CO₂ ceiling | 1000 ppm ("ASHRAE 62.1") | **900 ppm** (1-point) / **750 ppm** (2-point) | WELL A06 |
| Thermal comfort band | 19–26 °C | **21–25 °C** | WELL T01 |
| Illuminance (work plane) | 300 lux | **320 lux** | WELL / CIBSE SLL |
| Ambient noise (Cat 3, open areas) | 55 dBA | **tiered: 50 dBA (1-point) / 45 dBA (3-point)** | WELL S02 |

**Clause-attribution note (reconciled 2026-08-19).** The 900/750 ppm CO₂ values were attributed to A01, A03 and A06 in different places across this project's notes. Checked against the WELL v2 PDF itself, they belong to **A06 (Enhanced Ventilation Design, p. 26)**; A01 (Air Quality) carries the particulate-matter and inorganic-gas thresholds and remains the correct attribution for those benchmark items. A06 is used consistently from here on.

**Key correction:** ASHRAE 62.1 specifies *ventilation rates*, **not** a 1000 ppm CO₂ ceiling — a widespread misconception. Grounding in the actual standard both fixes the number and attributes it to a citable clause; an ungrounded model reproduces the myth. The real corpus acts as a "developing bath": a placeholder threshold silently propagates corpus → Monitor trigger → Planner goal → generated citation → benchmark gold, so the whole chain must be re-run end-to-end when the corpus changes.

**Honest caveat on the noise threshold.** The WELL S02 noise limit is **tiered by achievement level** (Category 3: 50 dBA at 1 point, 45 dBA at 3 points). The system uses **50 dBA**, which is the *1-point* threshold and is therefore defensible, not simply wrong. An earlier draft of this table over-corrected it to 45 (the stricter 3-point value); the accurate statement is that the value is tier-dependent, and that a benchmark question which does not name the tier (the original `noise-well` item) is ambiguous and should specify it. This is a smaller "corpus corrects the author" episode than first thought — the correction is *disambiguation*, not a flat error.
