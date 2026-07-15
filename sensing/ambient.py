"""sensing/ambient.py — synthetic-but-plausible room readings for the exhibit.

One model, two consumers, so the gauges and the history agree (a butler that reports a
22 degC weekly average while the screen shows 29 would give itself away):

  * the LIVE feed — RoomState.read_all() under settings.sim_ambient, i.e. what the kiosk
    gauges, the Monitor and the Q&A butler read right now;
  * the HISTORY backfill — ops/scripts/backfill_history.py, which replays this same model
    over the past fortnight so "average temperature last week" has data behind it.

Shape: a diurnal cycle (peak warmth/brightness ~14:00), a weekday-occupancy term, smooth
multi-period drift so the numbers breathe like a real room rather than jitter like noise,
and a little gaussian sensor noise on top.

`in_band=True` (the live feed) keeps every channel inside sensing/thresholds.py with margin.
That is deliberate: an ambient CO2 spike would open an incident the actuator cannot close —
the actuator drives RoomState's CO2 ODE, not this model — so the loop would replan and fail.
Anomalies on the exhibit come from deliberate injection, never from ambient drift.
`in_band=False` (history) allows real excursions — meeting spikes, dark nights — because no
Monitor judges the past, and "peak CO2 last week" needs something to find.

NOT real measurements. No LLM here — pure arithmetic.
"""

from __future__ import annotations

import math
import random
from datetime import datetime

# Anchored near the real baseline the hardware feed recorded, so the switch to simulated
# data does not visibly jump the room's character.
BASE = {"co2": 700.0, "temperature": 26.0, "humidity": 42.0, "lux": 450.0, "noise_db": 39.0}

# Live guard rails, comfortably inside THRESHOLDS (co2<=900, temp 21-32, hum 30-60,
# lux>=320, noise<=50) so noise near a limit can never trip the Monitor.
_IN_BAND = {
    "co2": (520.0, 860.0),
    "temperature": (22.0, 30.0),
    "humidity": (34.0, 56.0),
    "lux": (360.0, 620.0),
    "noise_db": (33.0, 47.0),
}


def _wander(ts: datetime, period_min: float, phase: float) -> float:
    """Smooth deterministic drift in [-1, 1]. Two incommensurate periods so the curve never
    looks like a clean sine — this is what makes a gauge read as 'alive' rather than noisy."""
    t = ts.timestamp() / 60.0
    a = math.sin(2 * math.pi * t / period_min + phase)
    b = math.sin(2 * math.pi * t / (period_min * 0.37) + phase * 2.0)
    return (a + 0.5 * b) / 1.5


def sample(ts: datetime, *, in_band: bool = True) -> dict[str, float]:
    """One plausible reading at wall-clock `ts`. See the module docstring for `in_band`."""
    h = ts.hour + ts.minute / 60.0
    day = 0.5 * (1 - math.cos(2 * math.pi * (h - 2) / 24))  # 0 ~02:00 → 1 ~14:00
    work = 1.0 if (ts.weekday() < 5 and 9 <= h <= 18) else 0.0

    out = {
        "co2": BASE["co2"] + work * 70 + 60 * _wander(ts, 23, 1.0) + 25 * _wander(ts, 6.3, 2.0),
        "temperature": BASE["temperature"] + (day - 0.5) * 2.4 + 0.6 * _wander(ts, 47, 3.0),
        "humidity": BASE["humidity"] - (day - 0.5) * 5 + 4 * _wander(ts, 53, 4.0),
        "lux": BASE["lux"] + day * 90 + 70 * _wander(ts, 31, 5.0),
        "noise_db": BASE["noise_db"] + day * 3 + work * 1.5 + 4 * _wander(ts, 3.1, 6.0),
    }
    for k, sigma in (
        ("co2", 6.0),
        ("temperature", 0.08),
        ("humidity", 0.4),
        ("lux", 8.0),
        ("noise_db", 0.8),
    ):
        out[k] += random.gauss(0, sigma)

    if not in_band:  # history only — give the stats something worth reporting
        if work and random.random() < 0.04:
            out["co2"] += random.uniform(300, 520)  # a packed meeting
        if not 7 <= h <= 19:
            out["lux"] = random.uniform(3, 35)  # lights off overnight
        out["co2"] = max(420.0, out["co2"])
        out["humidity"] = min(70.0, max(20.0, out["humidity"]))
        out["lux"] = max(0.0, out["lux"])
        out["noise_db"] = max(30.0, out["noise_db"])
    else:
        for k, (lo, hi) in _IN_BAND.items():
            out[k] = min(hi, max(lo, out[k]))

    return {
        "co2": round(out["co2"], 1),
        "temperature": round(out["temperature"], 1),
        "humidity": round(out["humidity"], 1),
        "lux": round(out["lux"], 1),
        "noise_db": round(out["noise_db"], 1),
    }
