"""ops/scripts/backfill_history.py — synthesise plausible past sensor_readings for a demo.

The Q&A butler answers "average temperature last week / peak CO2 today" from the
sensor_readings table (sensing.history.query_stats). The hardware feed (sensing.ingest)
only started recently, so long-window questions have no data yet. This one-off script
backfills the table with synthetic-but-plausible rows anchored to the CURRENT real
baseline plus a diurnal cycle and noise, so statistical questions return realistic curves
during a demo.

NOT real measurements — a clearly-labelled demo aid. Rows carry the same shape as real
ones; the live ingest feed keeps appending real rows on top. Safe to re-run (it only
inserts). To remove: DELETE FROM sensor_readings WHERE ts < <cutoff>.

    PYTHONPATH=. python ops/scripts/backfill_history.py --days 14 --step-min 10
"""

from __future__ import annotations

import argparse
import math
import random
from datetime import UTC, datetime, timedelta

from core.db import get_pool

# Current real baseline (measured 2026-06-27) — keep the backfill "about the same as now".
BASE = {"co2": 700.0, "temperature": 25.0, "humidity": 38.0, "lux": 400.0, "noise_db": 41.0}


def _sample(ts: datetime) -> dict[str, float]:
    """One plausible reading at wall-clock `ts`: baseline + diurnal cycle + noise.
    Peak warmth/brightness ~14:00; occupancy (CO2/noise) up on weekday work hours."""
    h = ts.hour + ts.minute / 60.0
    day = 0.5 * (1 - math.cos(2 * math.pi * (h - 2) / 24))  # 0 ~02:00 → 1 ~14:00
    work = 1.0 if (ts.weekday() < 5 and 9 <= h <= 18) else 0.0
    # CO2: occupancy-driven, higher on weekday work hours, occasional meeting spike.
    co2 = BASE["co2"] + work * random.uniform(60, 240) + random.gauss(0, 25)
    if work and random.random() < 0.04:
        co2 += random.uniform(300, 520)  # a packed-meeting spike → "peak CO2" has bite
    temp = BASE["temperature"] + (day - 0.5) * 2.4 + random.gauss(0, 0.3)  # warm afternoon
    hum = BASE["humidity"] - (day - 0.5) * 5 + random.gauss(0, 1.5)  # loosely inverse to temp
    # Lux: bright by day, near-dark at night (lights off).
    lux = (BASE["lux"] + day * 200 + random.gauss(0, 30)) if 7 <= h <= 19 else random.uniform(3, 35)
    noise = BASE["noise_db"] + day * 6 + work * 2 + random.gauss(0, 1.5)  # louder by day
    return {
        "co2": round(max(420.0, co2), 1),
        "temperature": round(temp, 1),
        "humidity": round(min(70.0, max(20.0, hum)), 1),
        "lux": round(max(0.0, lux), 1),
        "noise_db": round(max(30.0, noise), 1),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--step-min", type=int, default=10)
    args = ap.parse_args()
    now = datetime.now(UTC)
    start = now - timedelta(days=args.days)
    rows = []
    t = start
    while t < now:
        s = _sample(t)
        rows.append((t, s["co2"], s["temperature"], s["humidity"], s["lux"], s["noise_db"]))
        t += timedelta(minutes=args.step_min)
    with get_pool().connection() as conn, conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO sensor_readings (ts, co2, temperature, humidity, lux, noise_db) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            rows,
        )
    print(f"backfilled {len(rows)} rows from {start:%Y-%m-%d %H:%M} to {now:%Y-%m-%d %H:%M} UTC")


if __name__ == "__main__":
    main()
