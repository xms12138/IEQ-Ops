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
from datetime import UTC, datetime, timedelta

from core.db import get_pool
from sensing.ambient import sample

# The model lives in sensing/ambient.py so the live gauges and this backfill cannot drift
# apart — a butler quoting a weekly average that contradicts the screen would give the game
# away. in_band=False here: the past is not judged by the Monitor, so it keeps the meeting
# spikes and dark nights that make "peak CO2 last week" worth asking about.


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
        s = sample(t, in_band=False)
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
