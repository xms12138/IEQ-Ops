"""Deterministic sensor thresholds — the rules the Monitor judges against.

Kept as data (not prose buried in a prompt) so the Monitor prompt can render
them and so future "smarter monitoring" lands here as Python rules, never as
LLM cleverness (ops/llm_routing.md #1 ablate condition). Phase 1 only the CO2
line is wired to drive anomalies; the rest sit at safe values in the simulator.
"""

from __future__ import annotations

from typing import TypedDict


class Threshold(TypedDict):
    unit: str
    low: float | None  # below this is a violation (None = no lower bound)
    high: float | None  # above this is a violation (None = no upper bound)
    rule: str  # human/LLM-readable rule string rendered into the Monitor prompt


THRESHOLDS: dict[str, Threshold] = {
    "co2": {
        "unit": "ppm",
        "low": None,
        "high": 1000.0,
        "rule": "co2 must stay <= 1000 ppm (ASHRAE 62.1 indoor air-quality guideline)",
    },
    "temperature": {
        "unit": "degC",
        "low": 19.0,
        "high": 26.0,
        "rule": "temperature must stay within 19-26 degC (thermal comfort band)",
    },
    "humidity": {
        "unit": "%RH",
        "low": 30.0,
        "high": 60.0,
        "rule": "relative humidity must stay within 30-60 %RH",
    },
    "lux": {
        "unit": "lux",
        "low": 300.0,
        "high": None,
        "rule": "illuminance must stay >= 300 lux for occupied workspace (EN 12464-1)",
    },
    "noise_db": {
        "unit": "dBA",
        "low": None,
        "high": 55.0,
        "rule": "noise must stay <= 55 dBA in a working space",
    },
}


def rules_text() -> str:
    """One rule per line, for injection into the Monitor prompt."""
    return "\n".join(f"- {t['rule']}" for t in THRESHOLDS.values())
