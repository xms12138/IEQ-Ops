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
        "high": 900.0,
        "rule": "co2 must stay <= 900 ppm (WELL v2 Air, 1-point threshold)",
    },
    "temperature": {
        "unit": "degC",
        "low": 21.0,
        "high": 32.0,
        "rule": (
            "temperature must stay within 21-32 degC (exhibit summer band: comfort "
            "standards cap at ~25 degC per WELL v2 Thermal Comfort T01 / ASHRAE 55-2013, "
            "but the unconditioned exhibit room sits ~30 degC in a European summer, so the "
            "alert ceiling is raised to 32 degC to flag only genuine overheating)"
        ),
    },
    "humidity": {
        "unit": "%RH",
        "low": 30.0,
        "high": 60.0,
        "rule": "relative humidity must stay within 30-60 %RH",
    },
    "lux": {
        "unit": "lux",
        "low": 320.0,
        "high": None,
        "rule": (
            "illuminance must stay >= 320 lux at the task surface for "
            "offices/classrooms (WELL v2 Light, Predetermined light levels)"
        ),
    },
    "noise_db": {
        "unit": "dBA",
        "low": None,
        "high": 50.0,
        "rule": (
            "noise must stay <= 50 dBA average background "
            "(WELL v2 Sound S02 Maximum Noise Levels, Leq)"
        ),
    },
}


def rules_text() -> str:
    """One rule per line, for injection into the Monitor prompt."""
    return "\n".join(f"- {t['rule']}" for t in THRESHOLDS.values())
