"""procedural.py — SOP templates with trigger conditions (memory tier 3).

A procedural memory is a reusable Standard Operating Procedure: a trigger
condition plus an ordered set of steps, abstracted from RECURRING successful
trajectories — e.g. trigger "co2 > 1000 ppm in R1 during occupied hours", steps
["raise ventilation to high", "re-check in 15 min", "if still high, notify FM"].
The weekly Reflector drafts SOPs from the week's resolved incidents (cloud
deepseek-v4-pro — Hard Constraint #12, never local).

Output gating (ops/llm_routing.md #8, a hard safety floor): a reflector-drafted
SOP is NEVER active on write. It lands in status='pending' and a HUMAN must sign
off (approve_sop) before it can fire. A hallucinated SOP would silently corrupt
every future incident it triggers on, so the queue + sign-off is mandatory.

Storage: Postgres table `sops` (same database as incidents + checkpoints, separate
table). Postgres rather than Qdrant because an SOP is a structured record moving
through a review LIFECYCLE (pending → active | rejected) and matched by explicit
trigger conditions — not recalled by vector similarity. init_schema() creates the
table once at startup (explicit, no import side effects), mirroring mcp-ticket.

Hard Constraint #3: this module is the only writer/mutator of procedural memory,
and every state change (queue / approve / reject) emits an audit log line. SOP id:
SOP-{year}-{seq} (CLAUDE.md). seq is assigned serially by the consolidate node.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json
from pydantic import BaseModel, Field

from core.config import get_settings
from core.logging import get_logger

log = get_logger("procedural")


class SOPStatus(StrEnum):
    PENDING = "pending"  # reflector-drafted, awaiting human sign-off
    ACTIVE = "active"  # approved — may drive future incident handling
    REJECTED = "rejected"  # human rejected the draft


class SOPDraft(BaseModel):
    """An SOP as the Reflector proposes it — no id yet, always lands as PENDING."""

    title: str
    trigger_condition: str
    steps: list[str]
    incident_type: str  # airquality | thermal | lighting | acoustic
    evidence_ids: list[str] = Field(default_factory=list)


class SOPTemplate(BaseModel):
    """A persisted SOP across its review lifecycle."""

    sop_id: str
    title: str
    trigger_condition: str
    steps: list[str]
    incident_type: str
    evidence_ids: list[str]
    source_week: str
    status: SOPStatus


_DDL = """
CREATE TABLE IF NOT EXISTS sops (
    sop_id            text PRIMARY KEY,
    title             text NOT NULL,
    trigger_condition text NOT NULL,
    steps             jsonb NOT NULL,
    incident_type     text NOT NULL,
    evidence_ids      jsonb NOT NULL DEFAULT '[]',
    source_week       text NOT NULL,
    status            text NOT NULL DEFAULT 'pending',
    created_at        timestamptz NOT NULL DEFAULT now(),
    reviewed_at       timestamptz
);
"""


def _conn() -> psycopg.Connection[dict[str, Any]]:
    return psycopg.connect(get_settings().database_url, row_factory=dict_row)


def init_schema() -> None:
    """Create the sops table if absent. Run once at startup (mirrors mcp-ticket)."""
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(_DDL)
    log.info("procedural_schema_ready")


def _row_to_sop(row: dict[str, Any]) -> SOPTemplate:
    return SOPTemplate(
        sop_id=row["sop_id"],
        title=row["title"],
        trigger_condition=row["trigger_condition"],
        steps=row["steps"],  # jsonb → list (dict_row deserialises)
        incident_type=row["incident_type"],
        evidence_ids=row["evidence_ids"],
        source_week=row["source_week"],
        status=SOPStatus(row["status"]),
    )


def _next_seq(cur: Any, year: int) -> int:
    """Next within-year SOP sequence. Serial consolidate call → race-free."""
    cur.execute("SELECT count(*) AS n FROM sops WHERE sop_id LIKE %s", (f"SOP-{year}-%",))
    row = cur.fetchone()
    return (int(row["n"]) if row else 0) + 1


def queue_sop(draft: SOPDraft, *, week: str) -> str:
    """Queue ONE reflector-drafted SOP as PENDING (Hard Constraint #3 + the #8
    gating: never active on write). Returns the assigned SOP-{year}-{seq} id."""
    year = int(week.split("-")[0])
    with _conn() as conn, conn.cursor() as cur:
        seq = _next_seq(cur, year)
        sop_id = f"SOP-{year}-{seq:03d}"
        cur.execute(
            "INSERT INTO sops (sop_id, title, trigger_condition, steps, incident_type, "
            "evidence_ids, source_week, status) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                sop_id,
                draft.title,
                draft.trigger_condition,
                Json(draft.steps),
                draft.incident_type,
                Json(draft.evidence_ids),
                week,
                SOPStatus.PENDING.value,
            ),
        )
    log.info(  # audit
        "sop_queued", sop_id=sop_id, incident_type=draft.incident_type, n_steps=len(draft.steps)
    )
    return sop_id


def list_pending() -> list[SOPTemplate]:
    """All SOPs awaiting human sign-off — the review queue."""
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM sops WHERE status = %s ORDER BY created_at", (SOPStatus.PENDING.value,)
        )
        rows = cur.fetchall()
    return [_row_to_sop(r) for r in rows]


def _set_status(sop_id: str, status: SOPStatus) -> SOPTemplate:
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE sops SET status = %s, reviewed_at = now() WHERE sop_id = %s RETURNING *",
            (status.value, sop_id),
        )
        row = cur.fetchone()
    if row is None:
        raise ValueError(f"SOP {sop_id!r} not found")
    log.info("sop_reviewed", sop_id=sop_id, status=status.value)  # audit
    return _row_to_sop(row)


def approve_sop(sop_id: str) -> SOPTemplate:
    """Human sign-off: activate a pending SOP so it may drive future handling."""
    return _set_status(sop_id, SOPStatus.ACTIVE)


def reject_sop(sop_id: str) -> SOPTemplate:
    """Human sign-off: reject a pending SOP (kept for audit, never fires)."""
    return _set_status(sop_id, SOPStatus.REJECTED)


def active_sops(incident_type: str | None = None) -> list[SOPTemplate]:
    """Approved SOPs, optionally scoped to an incident type. Future readers: the
    planner / monitor preemptive-trigger matching (Phase 5+)."""
    query = "SELECT * FROM sops WHERE status = %s"
    params: list[Any] = [SOPStatus.ACTIVE.value]
    if incident_type:
        query += " AND incident_type = %s"
        params.append(incident_type)
    query += " ORDER BY created_at"
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(query, tuple(params))
        rows = cur.fetchall()
    return [_row_to_sop(r) for r in rows]
