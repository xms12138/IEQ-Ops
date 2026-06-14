"""core/suspend.py — registry of MainIncidentGraph threads suspended before verify.

The MainIncidentGraph suspends ~15 min between `action` and `verifier` (interrupt_before).
A long-running, unattended deployment needs SOMETHING to resume each suspended thread when
its window elapses, and to know which thread belongs to which incident. The scheduler
(ops/scheduler.py) owns that loop; this module is its durable registry.

Per the "external registry, don't touch the graph" decision: thread_id and incident_id
have no in-graph link, so the scheduler records the pair here the moment a scan suspends —
(thread_id, incident_id, resume_at) — reads back the due ones to resume, and discards them
once resumed. The table lives in the same Postgres (DDL in the ticket server's init_schema,
the single create-tables entry point). No LLM here.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import psycopg

from core.db import get_pool
from core.logging import get_logger

log = get_logger("suspend")


@contextmanager
def _conn() -> Iterator[psycopg.Connection[dict[str, Any]]]:
    with get_pool().connection() as conn:
        yield conn


def register(thread_id: str, incident_id: str, resume_at: datetime) -> None:
    """Record a thread that suspended before verify, to be resumed at resume_at.
    Idempotent on thread_id (re-registering updates the window)."""
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO suspended_threads (thread_id, incident_id, resume_at) "
            "VALUES (%s, %s, %s) ON CONFLICT (thread_id) DO UPDATE "
            "SET incident_id = EXCLUDED.incident_id, resume_at = EXCLUDED.resume_at",
            (thread_id, incident_id, resume_at),
        )
    log.info("suspend_registered", thread_id=thread_id, incident_id=incident_id)


def due(now: datetime | None = None) -> list[tuple[str, str]]:
    """(thread_id, incident_id) pairs whose resume_at has passed — ready to resume."""
    cutoff = now or datetime.now(UTC)
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT thread_id, incident_id FROM suspended_threads "
            "WHERE resume_at <= %s ORDER BY resume_at",
            (cutoff,),
        )
        rows = cur.fetchall()
    return [(str(r["thread_id"]), str(r["incident_id"])) for r in rows]


def discard(thread_id: str) -> None:
    """Drop a thread from the registry once it has been resumed (or is gone)."""
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM suspended_threads WHERE thread_id = %s", (thread_id,))
    log.info("suspend_discarded", thread_id=thread_id)


def thread_for_incident(incident_id: str) -> str | None:
    """The suspended thread_id parked for this incident, or None. Used by the operator
    dashboard's Tier-3 approval: a human decision must drop the parked thread so the
    scheduler's resume_tick does not later auto-fail it over the human's verdict."""
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT thread_id FROM suspended_threads WHERE incident_id = %s "
            "ORDER BY created_at DESC LIMIT 1",
            (incident_id,),
        )
        row = cur.fetchone()
    return str(row["thread_id"]) if row else None
