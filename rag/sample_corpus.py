"""Phase 2 placeholder corpus — hand-written standard excerpts, NOT the real PDFs.

The real ASHRAE 62.1 / WELL v2 / EN 16798-1 / EN 12464-1 PDFs go in `rag/corpus/`
(gitignored, copyright). Until they land, these short excerpts let the full
ingest→retrieve→Specialist pipeline run end to end on representative content.
They are paraphrased guidance values, safe to commit, and deliberately include
intra-domain distractors and cross-domain noise so retrieval (domain filter +
dual-path recall + rerank) has something real to discriminate.

`ingest.py` reads this in `--sample` mode; swap to PDF reading when corpus/ fills.
Each entry: one short standards passage, tagged with its domain and source id.
"""

from __future__ import annotations

SAMPLES: list[dict[str, str]] = [
    # ── airquality ────────────────────────────────────────────────────────────
    {
        "domain": "airquality",
        "source": "ashrae-62.1",
        "text": (
            "For office spaces, ASHRAE 62.1 sets a minimum outdoor air rate of "
            "8.5 L/s per person. Indoor CO2 concentration is an indirect indicator "
            "of whether ventilation keeps pace with occupancy, not a contaminant "
            "limit in itself."
        ),
    },
    {
        "domain": "airquality",
        "source": "ashrae-62.1",
        "text": (
            "When indoor CO2 rises above 1000 ppm, increase the mechanical "
            "ventilation rate or open operable windows until the concentration "
            "falls back below 800 ppm. Sustained levels above 1000 ppm indicate "
            "under-ventilation relative to the current occupant load."
        ),
    },
    {
        "domain": "airquality",
        "source": "en-16798-1",
        "text": (
            "EN 16798-1 classifies indoor air by CO2 increment above outdoor. "
            "Category I corresponds to +550 ppm, Category II to +800 ppm, and "
            "Category III to +1350 ppm above the outdoor concentration."
        ),
    },
    {
        "domain": "airquality",
        "source": "well-v2",
        "text": (
            "WELL v2 Air requires indoor CO2 not to exceed outdoor levels by more "
            "than 800 ppm, and calls for demand-controlled ventilation that "
            "responds dynamically in densely occupied spaces."
        ),
    },
    {
        "domain": "airquality",
        "source": "ops-note",
        "text": (
            "Fresh-air systems have a response lag of roughly 10 to 20 minutes. "
            "Raising the outdoor-air damper by about 20% typically lowers CO2 by "
            "150 to 300 ppm within 15 minutes in a moderately occupied room, so "
            "verification should allow a stabilisation window."
        ),
    },
    # ── thermal ───────────────────────────────────────────────────────────────
    {
        "domain": "thermal",
        "source": "ashrae-55",
        "text": (
            "ASHRAE 55 defines the operative temperature comfort zone for sedentary "
            "office work as roughly 20-24 degC in winter clothing and 23-26 degC in "
            "summer clothing, assuming 50% relative humidity and low air speed."
        ),
    },
    {
        "domain": "thermal",
        "source": "en-16798-1",
        "text": (
            "EN 16798-1 Category II sets the design operative temperature at "
            "20-25 degC for heating season and 23-26 degC for cooling season. "
            "Exceeding 26 degC for extended periods is treated as overheating."
        ),
    },
    {
        "domain": "thermal",
        "source": "ops-note",
        "text": (
            "When operative temperature climbs above 26 degC, increase cooling "
            "output or boost ventilation with cooler outdoor air; verify recovery "
            "into the comfort band before closing the incident."
        ),
    },
    # ── lighting ──────────────────────────────────────────────────────────────
    {
        "domain": "lighting",
        "source": "en-12464-1",
        "text": (
            "EN 12464-1 specifies a maintained illuminance of 500 lux on the task "
            "area for general office work such as writing, typing and reading. "
            "Corridors and circulation areas require only 100 lux."
        ),
    },
    {
        "domain": "lighting",
        "source": "en-12464-1",
        "text": (
            "Illuminance below 300 lux on an occupied workspace is insufficient for "
            "sustained visual tasks and should trigger an increase in luminaire "
            "output or a check for failed fittings."
        ),
    },
    # ── acoustic ──────────────────────────────────────────────────────────────
    {
        "domain": "acoustic",
        "source": "en-16798-1",
        "text": (
            "Recommended background noise in an open-plan office is below 45 dBA. "
            "Levels are driven by HVAC noise, external traffic and occupant "
            "activity."
        ),
    },
    {
        "domain": "acoustic",
        "source": "who-noise",
        "text": (
            "Continuous noise above 55 dBA in a working space disrupts "
            "concentration and raises annoyance; mitigation targets the source "
            "first, then adds absorption or masking."
        ),
    },
]
