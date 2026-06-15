"""frontend/api/ops.py — operator dashboard router (incident stream + injection).

The read side over the same Postgres `incidents` table the autonomous loop writes,
plus a scenario-injection trigger so a presenter can make the closed loop fire on
demand during an exhibit (instead of waiting for a real anomaly or the next 5-min
scan). No LLM here — the dashboard only renders what the loop produced and arms the
simulator.

Mounted on the same FastAPI app as the Q&A butler (frontend/api/main.py) via
`app.include_router(ops.router)`. Tier 3 human approval — resuming the graph that
blocked on autonomy_gate's interrupt() — is a separate concern wired on top of this.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastmcp.exceptions import ToolError

from core.checkpointer import open_checkpointer
from core.db import get_pool
from core.logging import get_logger
from core.state import IncidentStatus, tier_for_sensor
from core.suspend import discard as discard_thread
from core.suspend import thread_for_incident
from mcp_servers.client import call_tool
from mcp_servers.ticket.server import mcp as ticket_server
from sensing.simulator.scenarios import SCENARIOS, arm

log = get_logger("ops-dashboard")

router = APIRouter()
_APP_DIR = Path(__file__).resolve().parent.parent / "app"
_templates = Jinja2Templates(directory=str(_APP_DIR))

# Non-terminal statuses — summed into the header's "active" count (everything the loop
# is still working on, vs. the closed/failed terminals).
_ACTIVE_STATUSES = ("open", "planning", "diagnosing", "acting", "awaiting_approval", "verifying")

# One scan at a time. A presenter mashing the inject button must not spawn several
# concurrent graph compiles (each pulls the RAG stack + cloud calls); the Monitor's
# dedup already prevents duplicate incidents, this just caps the work.
_scan_lock = threading.Lock()


@router.get("/ops", response_class=HTMLResponse)
def ops_page(request: Request) -> Any:
    """The operator dashboard single page."""
    return _templates.TemplateResponse(request, "ops.html")


@router.get("/kiosk", response_class=HTMLResponse)
def kiosk_page(request: Request) -> Any:
    """The merged exhibit kiosk — incident stream + anomaly inject + Tier-3 approval card +
    voice Q&A on one screen (frontend/app/kiosk.html). The exhibit's single entry point: the
    audience sees the autonomous loop work AND can talk to the butler from the same display."""
    return _templates.TemplateResponse(request, "kiosk.html")


@router.get("/api/incidents")
def incidents(
    limit: int = 50, status: str | None = None, sensor: str | None = None
) -> JSONResponse:
    """Incident stream, newest-first — the read side of the autonomous loop."""
    rows = call_tool(ticket_server, "list_incidents", limit=limit, status=status, sensor=sensor)
    return JSONResponse(rows)


@router.get("/api/incidents/{incident_id}")
def incident_detail(incident_id: str) -> JSONResponse:
    """One incident's full record (drill-down). A missing id surfaces as get_incident's
    ValueError, which the in-memory MCP client re-raises as ToolError → return 404."""
    try:
        return JSONResponse(call_tool(ticket_server, "get_incident", incident_id=incident_id))
    except ToolError:
        return JSONResponse({"error": f"incident {incident_id!r} not found"}, status_code=404)


@router.get("/api/stats")
def stats() -> JSONResponse:
    """Incident counts by status for the header — one group-by, no LLM."""
    with get_pool().connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT status, count(*) AS n FROM incidents GROUP BY status")
        counts = {str(r["status"]): int(r["n"]) for r in cur.fetchall()}
    return JSONResponse(
        {
            "counts": counts,
            "active": sum(counts.get(s, 0) for s in _ACTIVE_STATUSES),
            "closed": counts.get("closed", 0),
            "failed": counts.get("failed", 0),
            "total": sum(counts.values()),
        }
    )


@router.get("/api/scenarios")
def scenarios() -> JSONResponse:
    """The injectable demo scenarios (name + human one-liner) for the inject panel."""
    return JSONResponse(
        [
            {
                "name": s.name,
                "description": s.description,
                "sensor": s.expected_sensor,
                "domain": s.expected_domain,
                "closes_loop": s.closes_loop,
                # Action tier the autonomy_gate will assign (1 = auto-resolve, 3 = needs human
                # approval). Derived from the sensor's domain, not stored — so the panel can
                # badge each scenario "auto" vs "needs approval" without a second source of truth.
                "tier": int(tier_for_sensor(s.expected_sensor)),
            }
            for s in SCENARIOS.values()
            if s.exhibit_safe  # hide replan/FAILED demos (co2_overcrowded) from the live panel
        ]
    )


@router.post("/api/inject")
def inject(scenario: str = Form(...)) -> JSONResponse:
    """Arm a named scenario and kick one scan in the background so the injected anomaly
    becomes a live incident within seconds, not at the next 5-min tick. Returns immediately;
    the new incident shows up in the stream as the scan progresses."""
    sc = SCENARIOS.get(scenario)
    if sc is None:
        return JSONResponse(
            {"ok": False, "error": f"unknown scenario {scenario!r}"}, status_code=400
        )
    if not sc.exhibit_safe:
        # co2_overcrowded & friends are replan/FAILED demos — paper/CLI only, never injected live.
        return JSONResponse(
            {"ok": False, "error": f"scenario {scenario!r} is paper/CLI-only (not exhibit-safe)"},
            status_code=403,
        )
    arm(scenario)
    threading.Thread(target=_scan_now, name=f"inject-{scenario}", daemon=True).start()
    log.info("ops_inject", scenario=scenario)
    return JSONResponse(
        {"ok": True, "scenario": scenario, "description": SCENARIOS[scenario].description}
    )


@router.post("/api/incidents/{incident_id}/decision")
def decide(incident_id: str, decision: str = Form(...)) -> JSONResponse:
    """Tier-3 human decision from the dashboard. SCOPE: bookkeeping, not a graph resume —
    it closes/fails the ticket and drops the parked thread + checkpoint, it does NOT drive
    the autonomy_gate interrupt() (a deliberate, labelled limitation; the durable interrupt
    stays as the architecture's Tier-3 block). Dropping the thread is what stops the
    scheduler's resume_tick from later auto-failing it over the operator's verdict."""
    if decision not in ("approve", "reject"):
        return JSONResponse({"ok": False, "error": "decision must be approve|reject"}, 400)
    try:
        inc = call_tool(ticket_server, "get_incident", incident_id=incident_id)
    except ToolError:
        return JSONResponse({"error": f"incident {incident_id!r} not found"}, status_code=404)
    if inc["status"] != IncidentStatus.AWAITING_APPROVAL.value:
        return JSONResponse(
            {"ok": False, "error": f"incident is {inc['status']}, not awaiting approval"}, 409
        )

    approved = decision == "approve"
    new_status = IncidentStatus.CLOSED if approved else IncidentStatus.FAILED
    note = "resolved by human approval (Tier 3)" if approved else "rejected by operator (Tier 3)"
    call_tool(
        ticket_server,
        "update_incident",
        incident_id=incident_id,
        status=new_status.value,
        action_taken=note,
    )
    # Drop the parked thread (+ its checkpoint) so the scheduler does not resume it later.
    tid = thread_for_incident(incident_id)
    if tid is not None:
        try:
            with open_checkpointer() as cp:
                cp.delete_thread(tid)
        except Exception as exc:  # noqa: BLE001 — checkpoint cleanup is best-effort
            log.warning("ops_checkpoint_delete_failed", thread_id=tid, error=str(exc))
        discard_thread(tid)
    log.info("ops_tier3_decision", incident_id=incident_id, decision=decision, thread_id=tid)
    return JSONResponse({"ok": True, "incident_id": incident_id, "status": new_status.value})


def _scan_now() -> None:
    """Run one scheduler scan, single-flight. Imported lazily — scan_tick pulls in the whole
    graph (specialists, RAG, cloud LLM), which we don't want loaded at module import (the
    page route must stay light). A demo trigger must never take the gateway down, so every
    failure is swallowed to a log line."""
    if not _scan_lock.acquire(blocking=False):
        log.info("ops_scan_skipped_busy")
        return
    try:
        from ops.scheduler import scan_tick

        # wait=True: block for the cross-process scan advisory lock so the presenter's inject
        # is never dropped just because the scheduler's heartbeat scan is mid-flight.
        scan_tick(wait=True)
    except Exception as exc:  # noqa: BLE001 — demo trigger, never propagate to the request
        log.warning("ops_scan_failed", error=str(exc))
    finally:
        _scan_lock.release()
