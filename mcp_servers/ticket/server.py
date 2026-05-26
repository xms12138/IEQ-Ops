"""mcp-ticket-server — FastMCP, incident CRUD on Postgres.

The incidents table is the durable record of every anomaly the system handles;
it lives in the same Postgres as the LangGraph checkpoints (separate tables).
init_schema() is called explicitly at startup, not on import, to avoid import
side effects. No LLM here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import psycopg
from fastmcp import FastMCP
from psycopg.rows import dict_row

from core.config import get_settings
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

# sensor → incident-type code used in the incident id (CLAUDE.md I-{date}-{room}-{type})
_SENSOR_TYPE = {"co2": "AQ", "temperature": "TH", "humidity": "TH", "lux": "LT", "noise_db": "AC"}


def _conn() -> psycopg.Connection[dict[str, Any]]:
    return psycopg.connect(get_settings().database_url, row_factory=dict_row)


def init_schema() -> None:
    """Create the incidents table if absent. Run once at startup."""
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(_DDL)
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
