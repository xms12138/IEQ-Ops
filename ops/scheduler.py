"""ops/scheduler.py — the autonomous heartbeat for MainIncidentGraph.

The minimum a long-running deployment needs beyond the manual run_incident.py driver:
two APScheduler interval jobs.

  scan   — every SCAN_INTERVAL_MIN: run one monitor→…→action pass on the CURRENT sensor
           readings. Monitor dedups (no duplicate incident for an ongoing anomaly), so a
           tick with no NEW anomaly just ends. A newly opened incident suspends before
           verify and is registered (core.suspend) for later resume; a terminal tick
           (no anomaly / dedup / critic END) has its checkpoint purged immediately (#10).
  resume — every RESUME_INTERVAL_MIN: resume each suspended thread whose window has
           elapsed → verifier closes/fails it, then its checkpoint is purged (#10).

Deployment (exhibit): the Pi runs the FULL stack — this scheduler, the Q&A web, Postgres,
Qdrant, and the CPU RAG. Two consequences shape the code here:

  * Cross-process single-flight. scan_tick runs in BOTH this process (the 5-min heartbeat)
    and the web process (inject → scan); each compile pulls the RAG stack (~3.8 GiB), so two
    concurrent scans would OOM the 8 GB Pi. A Postgres SESSION advisory lock (whole-machine)
    serialises them — the in-process lock in ops.py cannot reach across processes. A
    no-anomaly heartbeat scan releases in seconds (Monitor judges and ends before RAG), so
    the web inject path blocks on the lock (never dropping a presenter's click) while the
    heartbeat skips a contended tick (dedup means it loses nothing).
  * Simulator stands in for the world. On the exhibit (sensor_source == "sim") the room only
    evolves via advance_minutes(), never wall-clock — so resume fast-forwards the room across
    the verify window before the Verifier reads, else it sees the injected value unchanged →
    a false "missed" → a needless replan. With real hardware (sensor_source == "hardware")
    the world moves on its own and resume must NOT touch the simulator. exhibit_mode also
    compresses the wall-clock resume wait to verify_window_seconds so a visitor sees the
    incident close in ~90 s instead of the real 15 min.
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

from apscheduler.schedulers.blocking import BlockingScheduler
from langchain_core.runnables import RunnableConfig
from pydantic import ValidationError

from core.checkpointer import open_checkpointer
from core.config import get_settings
from core.db import get_pool
from core.graph import INTERRUPT_BEFORE, build_main_graph
from core.logging import configure_logging, get_logger
from core.state import MainIncidentState
from core.suspend import discard, due, register
from mcp_servers.ticket.server import init_schema
from sensing.simulator.room import reload_room, save_room

log = get_logger("scheduler")

SCAN_INTERVAL_MIN = 5
RESUME_INTERVAL_MIN = 1
_DEFAULT_TARGET_MIN = 15
# Fixed application key for the whole-machine scan advisory lock; the web inject path
# (frontend/api/ops.py) takes the same key. Any constant both processes agree on works.
_SCAN_LOCK_KEY = 0x1E905CA4


def _config(thread_id: str) -> RunnableConfig:
    return {"configurable": {"thread_id": thread_id}}


@contextlib.contextmanager
def _scan_single_flight(wait: bool) -> Iterator[bool]:
    """Whole-machine single-flight for scan_tick via a Postgres SESSION advisory lock, held
    on a pooled connection for the scan's lifetime and released explicitly (a pool reset on
    return does NOT drop a session-level advisory lock). wait=False (heartbeat) yields False
    on contention and skips; wait=True (web inject) blocks until the lock is free so a
    presenter's click is never dropped."""
    with get_pool().connection() as conn, conn.cursor() as cur:
        if wait:
            cur.execute("SELECT pg_advisory_lock(%s)", (_SCAN_LOCK_KEY,))  # blocks until held
            got = True
        else:
            cur.execute("SELECT pg_try_advisory_lock(%s) AS got", (_SCAN_LOCK_KEY,))
            got = bool(cur.fetchone()["got"])
        try:
            yield got
        finally:
            if got:
                cur.execute("SELECT pg_advisory_unlock(%s)", (_SCAN_LOCK_KEY,))


def _target_minutes(values: dict[str, Any]) -> int:
    """Resume window = the primary subtask's target_time_min (default 15)."""
    try:
        result = MainIncidentState.model_validate(values).primary_result()
        if result is not None:
            return result.expected_outcome.target_time_min
        return _DEFAULT_TARGET_MIN
    except (ValidationError, AttributeError):
        return _DEFAULT_TARGET_MIN


def _resume_delta(values: dict[str, Any]) -> timedelta:
    """How long after suspend to resume. exhibit_mode compresses the wall-clock wait to a
    fixed short window (the audience watches the close happen ~90 s after the action);
    otherwise it is the real per-incident verify horizon (target_time_min)."""
    settings = get_settings()
    if settings.exhibit_mode:
        return timedelta(seconds=settings.verify_window_seconds)
    return timedelta(minutes=_target_minutes(values))


def _advance_sim_before_verify(minutes: int) -> None:
    """Sim-only: fast-forward the room across the verify window so the Verifier reads the
    post-action recovery, not the injected anomaly value. The web process persisted the
    post-action room (raised ventilation); reload_room() pulls that state into this separate
    scheduler process before integrating the CO2 ODE forward. Gated by sensor_source == 'sim'
    at the call site — with real hardware the world moves on its own."""
    room = reload_room()
    room.advance_minutes(minutes)
    save_room()
    log.info("sim_advanced_for_verify", minutes=minutes, co2=room.read_co2())


def scan_tick(wait: bool = False) -> None:
    """One monitor→…→action pass on the current readings; register a suspend or purge.
    wait — block for the cross-process scan lock (web inject path) vs skip if contended
    (scheduler heartbeat)."""
    with _scan_single_flight(wait) as got:
        if not got:
            log.info("scan_skipped_locked")  # another process is mid-scan; dedup covers us
            return
        reload_room()  # simulator file is the cross-process truth — pick up a scenario the
        #               web process just armed, not this process's stale cache.
        tid = f"thr-{uuid.uuid4().hex[:12]}"
        with open_checkpointer() as cp:
            graph = build_main_graph().compile(checkpointer=cp, interrupt_before=INTERRUPT_BEFORE)
            graph.invoke(MainIncidentState(), _config(tid))
            snap = graph.get_state(_config(tid))
            if snap.next:  # suspended before verifier → register for later resume
                incident_id = str(snap.values.get("incident_id"))
                resume_at = datetime.now(UTC) + _resume_delta(snap.values)
                register(tid, incident_id, resume_at)
                log.info("scan_suspended", thread_id=tid, incident_id=incident_id)
            else:  # terminal (no anomaly / dedup / critic END) → checkpoint no longer needed
                cp.delete_thread(tid)
                log.info("scan_terminal", thread_id=tid, status=str(snap.values.get("status")))


def resume_tick() -> None:
    """Resume every suspended thread whose window has elapsed; purge each when done.

    A "missed" verdict replans (verifier → replan → planner → … → action) and suspends
    the SAME thread before verify a second time. So after resuming, re-check snap.next:
    a still-suspended thread is re-registered for a fresh window (its checkpoint lives on)
    rather than purged — only a terminal thread is discarded (#10)."""
    pending = due()
    if not pending:
        return
    sim = get_settings().sensor_source == "sim"
    with open_checkpointer() as cp:
        graph = build_main_graph().compile(checkpointer=cp, interrupt_before=INTERRUPT_BEFORE)
        for tid, incident_id in pending:
            snap = graph.get_state(_config(tid))
            if snap.next:
                # A verifier-suspended thread on the sim exhibit: fast-forward the room so the
                # Verifier reads the post-action recovery, not the injected value (else a false
                # "missed" → replan). A Tier-3 thread parked at autonomy_gate (awaiting a human)
                # is NOT advanced — it resumes via the dashboard decision, not the clock — so
                # gate on the verifier being the actual suspend point.
                if sim and "verifier" in snap.next:
                    _advance_sim_before_verify(_target_minutes(snap.values))
                graph.invoke(None, _config(tid))  # verifier → (close/fail | replan → re-suspend)
                final = graph.get_state(_config(tid))
                if final.next:  # replanned on a miss → suspended again before verify
                    resume_at = datetime.now(UTC) + _resume_delta(final.values)
                    register(tid, incident_id, resume_at)  # idempotent upsert → new window
                    log.info("resume_replanned", thread_id=tid, incident_id=incident_id)
                    continue  # keep the thread + checkpoint alive for the next window
                log.info(
                    "resume_done",
                    thread_id=tid,
                    incident_id=incident_id,
                    status=str(final.values.get("status")),
                )
            else:  # already advanced past the suspend point elsewhere
                log.info("resume_skip_gone", thread_id=tid, incident_id=incident_id)
            discard(tid)
            cp.delete_thread(tid)  # incident now terminal → purge checkpoint (#10)


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    init_schema()  # ensure incidents + sensor_readings + suspended_threads exist
    log.info(
        "scheduler_start",
        scan_min=SCAN_INTERVAL_MIN,
        resume_min=RESUME_INTERVAL_MIN,
        sensor_source=settings.sensor_source,
        exhibit_mode=settings.exhibit_mode,
    )
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        scan_tick, "interval", minutes=SCAN_INTERVAL_MIN, max_instances=1, coalesce=True
    )
    scheduler.add_job(
        resume_tick, "interval", minutes=RESUME_INTERVAL_MIN, max_instances=1, coalesce=True
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("scheduler_stop")


if __name__ == "__main__":
    main()
