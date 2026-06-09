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

Runs on the box with the GPU (a scan can reach the Specialist RAG retrieve); the Pi runs
only the sampler + Q&A web. Resume does NOT advance the simulator — this is a production
component on wall-clock time (demo.py / run_incident.py keep the sim-advance path).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from apscheduler.schedulers.blocking import BlockingScheduler
from langchain_core.runnables import RunnableConfig
from pydantic import ValidationError

from core.checkpointer import open_checkpointer
from core.config import get_settings
from core.graph import INTERRUPT_BEFORE, build_main_graph
from core.logging import configure_logging, get_logger
from core.state import MainIncidentState
from core.suspend import discard, due, register
from mcp_servers.ticket.server import init_schema

log = get_logger("scheduler")

SCAN_INTERVAL_MIN = 5
RESUME_INTERVAL_MIN = 1
_DEFAULT_TARGET_MIN = 15


def _config(thread_id: str) -> RunnableConfig:
    return {"configurable": {"thread_id": thread_id}}


def _target_minutes(values: dict[str, Any]) -> int:
    """Resume window = the primary subtask's target_time_min (default 15)."""
    try:
        result = MainIncidentState.model_validate(values).primary_result()
        if result is not None:
            return result.expected_outcome.target_time_min
        return _DEFAULT_TARGET_MIN
    except (ValidationError, AttributeError):
        return _DEFAULT_TARGET_MIN


def scan_tick() -> None:
    """One monitor→…→action pass on the current readings; register a suspend or purge."""
    tid = f"thr-{uuid.uuid4().hex[:12]}"
    with open_checkpointer() as cp:
        graph = build_main_graph().compile(checkpointer=cp, interrupt_before=INTERRUPT_BEFORE)
        graph.invoke(MainIncidentState(), _config(tid))
        snap = graph.get_state(_config(tid))
        if snap.next:  # suspended before verifier → register for later resume
            incident_id = str(snap.values.get("incident_id"))
            resume_at = datetime.now(UTC) + timedelta(minutes=_target_minutes(snap.values))
            register(tid, incident_id, resume_at)
            log.info("scan_suspended", thread_id=tid, incident_id=incident_id)
        else:  # terminal (no anomaly / dedup / critic END) → checkpoint no longer needed
            cp.delete_thread(tid)
            log.info("scan_terminal", thread_id=tid, status=str(snap.values.get("status")))


def resume_tick() -> None:
    """Resume every suspended thread whose window has elapsed; purge each when done."""
    pending = due()
    if not pending:
        return
    with open_checkpointer() as cp:
        graph = build_main_graph().compile(checkpointer=cp, interrupt_before=INTERRUPT_BEFORE)
        for tid, incident_id in pending:
            snap = graph.get_state(_config(tid))
            if snap.next:
                graph.invoke(None, _config(tid))  # continue from checkpoint → verifier → END
                final = graph.get_state(_config(tid))
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
    log.info("scheduler_start", scan_min=SCAN_INTERVAL_MIN, resume_min=RESUME_INTERVAL_MIN)
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
