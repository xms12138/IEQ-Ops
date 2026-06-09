"""mcp-ticket-server — FastMCP, incident CRUD on Postgres.

The incidents table is the durable record of every anomaly the system handles;
it lives in the same Postgres as the LangGraph checkpoints (separate tables).
init_schema() is called explicitly at startup, not on import, to avoid import
side effects. No LLM here.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import psycopg
from fastmcp import FastMCP

from core.db import get_pool
from core.logging import get_logger

log = get_logger("mcp-ticket")
mcp = FastMCP("mcp-ticket-server")

_DDL = """
CREATE TABLE IF NOT EXISTS incidents (
    incident_id   text PRIMARY KEY,
    status        text NOT NULL,
    sensor        text NOT NULL,
    value         double precision NOT NULL,
    rule_violated text NOT NULL,
    action_taken  text,
    verdict       text,
    delta         double precision,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
);
"""

# sensor_readings: a flat time series for the Q&A butler's statistical questions
# (sensing/history.py writes via the sampler, reads via query_stats). A different
# concern from incidents, but co-located here so init_schema stays the single
# create-tables entry point. Phase 5 can move it to InfluxDB.
_READINGS_DDL = """
CREATE TABLE IF NOT EXISTS sensor_readings (
    ts          timestamptz NOT NULL DEFAULT now(),
    co2         double precision,
    temperature double precision,
    humidity    double precision,
    lux         double precision,
    noise_db    double precision
);
"""
_READINGS_INDEX = "CREATE INDEX IF NOT EXISTS sensor_readings_ts_idx ON sensor_readings (ts)"

# suspended_threads: scheduler's registry of MainIncidentGraph threads paused before
# verify (core/suspend.py reads/writes it). Co-located here so init_schema stays the
# single create-tables entry point; the registry links thread_id ↔ incident_id, which
# the graph itself does not persist.
_SUSPENDED_DDL = """
CREATE TABLE IF NOT EXISTS suspended_threads (
    thread_id   text PRIMARY KEY,
    incident_id text NOT NULL,
    resume_at   timestamptz NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);
"""

# sensor → incident-type code used in the incident id (CLAUDE.md I-{date}-{room}-{type})
_SENSOR_TYPE = {"co2": "AQ", "temperature": "TH", "humidity": "TH", "lux": "LT", "noise_db": "AC"}


@contextmanager
def _conn() -> Iterator[psycopg.Connection[dict[str, Any]]]:
    with get_pool().connection() as conn:
        yield conn


def init_schema() -> None:
    """Create the incidents + sensor_readings + suspended_threads tables if absent.
    Run once at startup."""
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(_DDL)
        cur.execute(_READINGS_DDL)
        cur.execute(_READINGS_INDEX)
        cur.execute(_SUSPENDED_DDL)
    log.info("ticket_schema_ready")


@mcp.tool
def create_incident(sensor: str, value: float, rule_violated: str, room: str = "R1") -> str:
    """Open a new incident from a Monitor anomaly. Returns the incident_id."""
    now = datetime.now(UTC)
    type_code = _SENSOR_TYPE.get(sensor, "XX")
    incident_id = f"I-{now:%Y%m%d}-{room}-{type_code}-{now:%H%M%S}"
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO incidents (incident_id, status, sensor, value, rule_violated) "
            "VALUES (%s, %s, %s, %s, %s)",
            (incident_id, "open", sensor, value, rule_violated),
        )
    log.info("incident_created", incident_id=incident_id, sensor=sensor, value=value)
    return incident_id


@mcp.tool
def active_incident_for_sensor(sensor: str) -> str | None:
    """Most recent UNRESOLVED incident id for this sensor (status not closed/failed),
    or None. Lets the Monitor skip opening a duplicate for an anomaly that is already
    being handled — a persistent anomaly must not spawn a new incident every 5-min scan."""
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT incident_id FROM incidents "
            "WHERE sensor = %s AND status NOT IN ('closed', 'failed') "
            "ORDER BY created_at DESC LIMIT 1",
            (sensor,),
        )
        row = cur.fetchone()
    return str(row["incident_id"]) if row else None


@mcp.tool
def update_incident(
    incident_id: str,
    status: str | None = None,
    action_taken: str | None = None,
    verdict: str | None = None,
    delta: float | None = None,
) -> dict[str, Any]:
    """Patch the mutable fields of an incident. Only non-None fields are written."""
    fields = {
        "status": status,
        "action_taken": action_taken,
        "verdict": verdict,
        "delta": delta,
    }
    sets = {k: v for k, v in fields.items() if v is not None}
    if not sets:
        return get_incident(incident_id)
    assignments = ", ".join(f"{k} = %s" for k in sets)
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"UPDATE incidents SET {assignments}, updated_at = now() WHERE incident_id = %s",
            (*sets.values(), incident_id),
        )
    log.info("incident_updated", incident_id=incident_id, **sets)
    return get_incident(incident_id)


@mcp.tool
def get_incident(incident_id: str) -> dict[str, Any]:
    """Fetch a single incident as a dict (timestamps ISO-formatted)."""
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM incidents WHERE incident_id = %s", (incident_id,))
        row = cur.fetchone()
    if row is None:
        raise ValueError(f"incident {incident_id!r} not found")
    for k in ("created_at", "updated_at"):
        if row.get(k) is not None:
            row[k] = row[k].isoformat()
    return row


@mcp.tool
def list_incidents(
    limit: int = 50, status: str | None = None, sensor: str | None = None
) -> list[dict[str, Any]]:
    """List incidents newest-first (timestamps ISO-formatted), optionally filtered
    by status and/or sensor. Read side for the Q&A butler's 'recent anomalies'
    questions — no LLM here."""
    query = "SELECT * FROM incidents"
    conds: list[str] = []
    params: list[Any] = []
    if status is not None:
        conds.append("status = %s")
        params.append(status)
    if sensor is not None:
        conds.append("sensor = %s")
        params.append(sensor)
    if conds:
        query += " WHERE " + " AND ".join(conds)
    query += " ORDER BY created_at DESC LIMIT %s"
    params.append(limit)
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(query, tuple(params))
        rows = cur.fetchall()
    for row in rows:
        for k in ("created_at", "updated_at"):
            if row.get(k) is not None:
                row[k] = row[k].isoformat()
    return rows
