"""sensing/history.py — raw sensor-reading history for the Q&A butler.

A lightweight flat time series written by ops/sampler.py (read_sensors →
record_reading every SAMPLE_INTERVAL_SECONDS) and read back by the
ConversationalAgent for statistical questions ("past-24h average CO2").

This is NOT InfluxDB (Phase 5) and NOT the incident loop — just the
`sensor_readings` table in the same Postgres as incidents. The table DDL lives
in mcp_servers/ticket/server.py::init_schema (single create-tables entry point);
this module only reads/writes rows, reusing the same dict_row connection pattern.
No LLM here.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
from pydantic import BaseModel

from core.db import get_pool
from core.logging import get_logger

log = get_logger("history")

# The sampleable sensor columns — also the ONLY legal `sensor` args below. A column
# name cannot be a bind parameter, so it is interpolated into SQL; membership in this
# tuple is checked first, which is what makes that interpolation injection-safe.
SENSOR_COLUMNS = ("co2", "temperature", "humidity", "lux", "noise_db")

# In-band fallbacks for read_sensors under sensor_source=='hardware' when the table is empty
# (cold start before the first ingest frame) or a column is NULL — they match the simulator's
# RoomState defaults so the Monitor never crashes or false-fires on startup. A real frame
# overwrites these within seconds (the firmware publishes every 5 s).
_SAFE_DEFAULTS: dict[str, float] = {
    "co2": 650.0,
    "temperature": 22.5,
    "humidity": 45.0,
    "lux": 420.0,
    "noise_db": 41.0,
}

_WINDOW_RE = re.compile(r"^\s*(\d+)\s*([mhd])\s*$", re.IGNORECASE)
_UNIT = {"m": "minutes", "h": "hours", "d": "days"}


class ReadingStats(BaseModel):
    """Aggregate of one sensor over a trailing window (avg/min/max None when no rows)."""

    sensor: str
    since_hours: float
    n: int
    avg: float | None = None
    min: float | None = None
    max: float | None = None
    latest: float | None = None


@contextmanager
def _conn() -> Iterator[psycopg.Connection[dict[str, Any]]]:
    with get_pool().connection() as conn:
        yield conn


def _f(x: Any) -> float | None:
    return round(float(x), 2) if x is not None else None


def parse_window(value: str | None, *, default: timedelta) -> timedelta:
    """Parse a window like '30m' / '24h' / '7d' into a timedelta. Falls back to
    `default` on None or unrecognised input (the dispatch LLM may omit `since`)."""
    if not value:
        return default
    m = _WINDOW_RE.match(value)
    if not m:
        return default
    return timedelta(**{_UNIT[m.group(2).lower()]: int(m.group(1))})


def record_reading(readings: dict[str, float]) -> None:
    """Append one sample row; sensors absent from `readings` are stored NULL.
    Called by the sampler — never runs the incident graph."""
    values = [readings.get(c) for c in SENSOR_COLUMNS]
    placeholders = ", ".join(["%s"] * len(SENSOR_COLUMNS))
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"INSERT INTO sensor_readings ({', '.join(SENSOR_COLUMNS)}) VALUES ({placeholders})",
            values,
        )
    log.info("reading_recorded", **{c: readings.get(c) for c in SENSOR_COLUMNS})


def query_stats(sensor: str, since: timedelta) -> ReadingStats:
    """avg/min/max/latest/n for one sensor over the trailing `since` window."""
    if sensor not in SENSOR_COLUMNS:
        raise ValueError(f"unknown sensor {sensor!r}; expected one of {SENSOR_COLUMNS}")
    cutoff = datetime.now(UTC) - since
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT avg({sensor}) AS avg, min({sensor}) AS min, max({sensor}) AS max, "
            f"count({sensor}) AS n FROM sensor_readings WHERE ts >= %s",
            (cutoff,),
        )
        agg = cur.fetchone() or {}
        cur.execute(
            f"SELECT {sensor} AS v FROM sensor_readings "
            f"WHERE {sensor} IS NOT NULL ORDER BY ts DESC LIMIT 1"
        )
        last = cur.fetchone()
    return ReadingStats(
        sensor=sensor,
        since_hours=round(since.total_seconds() / 3600, 2),
        n=int(agg.get("n") or 0),
        avg=_f(agg.get("avg")),
        min=_f(agg.get("min")),
        max=_f(agg.get("max")),
        latest=_f(last["v"]) if last else None,
    )


def recent(sensor: str, since: timedelta, limit: int = 500) -> list[tuple[str, float]]:
    """Raw (ISO-ts, value) series for one sensor, newest first. For future charts."""
    if sensor not in SENSOR_COLUMNS:
        raise ValueError(f"unknown sensor {sensor!r}; expected one of {SENSOR_COLUMNS}")
    cutoff = datetime.now(UTC) - since
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT ts, {sensor} AS v FROM sensor_readings "
            f"WHERE ts >= %s AND {sensor} IS NOT NULL ORDER BY ts DESC LIMIT %s",
            (cutoff, limit),
        )
        rows = cur.fetchall()
    return [(r["ts"].isoformat(), float(r["v"])) for r in rows]


def latest_reading() -> dict[str, float]:
    """The most recent sensor_readings row as a {sensor: value} dict — the hardware source
    for read_sensors under sensor_source=='hardware'. An empty table or a NULL column falls
    back to the in-band safe default for that sensor, so the Monitor reads a complete, valid
    frame even before the first ingest message or while a channel is still uncalibrated."""
    cols = ", ".join(SENSOR_COLUMNS)
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT {cols} FROM sensor_readings ORDER BY ts DESC LIMIT 1")
        row = cur.fetchone()
    out: dict[str, float] = {}
    for c in SENSOR_COLUMNS:
        v = row.get(c) if row else None
        out[c] = float(v) if v is not None else _SAFE_DEFAULTS[c]
    return out
