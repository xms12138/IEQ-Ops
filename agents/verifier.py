"""VerifierAgent — node `verifier.check` (ops/llm_routing.md #6).

Runs 15 (simulated) minutes after the action. Reads the target metric again and
checks it against the specialist's declared ExpectedOutcome (Hard Constraint #13)
— a pure numeric comparison, which is exactly why this can run on the LOCAL tier
(Qwen3-8B in prod; dev override → deepseek-v4-flash). Closes the incident on
"met"; on "missed" it routes back to the planner for a fresh attempt while replan
budget remains (status PLANNING → _route_after_verifier → replan), and only fails the
incident once the budget is spent (CLAUDE.md Principle #2 — a failed intervention
triggers replan, not silence). The finished trajectory is written to Episodic Memory
only on a TERMINAL verdict (Hard Constraint #3 — through memory/episodic.py, never an
inline upsert here); a retry's interim miss is not the incident's outcome.

A deterministic Python comparison backs the LLM up; Phase 1 handles the CO2
upper-bound case only.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from agents.prompt_loader import load_prompt
from core.logging import get_logger
from core.router import Router, RouterExhausted
from core.state import (
    ExpectedOutcome,
    IncidentStatus,
    MainIncidentState,
    VerifierVerdict,
    replans_left,
)
from mcp_servers.client import call_tool
from mcp_servers.sensor.server import mcp as sensor_server
from mcp_servers.ticket.server import mcp as ticket_server
from memory.episodic import save_trajectory

log = get_logger("verifier")


class VerifierAgent:
    def __init__(self, router: Router | None = None) -> None:
        self.router = router or Router()
        self._template = load_prompt("verifier")

    def run(self, state: MainIncidentState) -> dict[str, Any]:
        # P-009: verify the SAME subtask the action acted on — the primary (its domain
        # matches the anomaly's sensor), not whatever happens to be first in the dict.
        # With a multi-subtask DAG `next(iter(...))` could pick an advisory subtask and
        # verify the wrong metric. autonomy_gate / action already key off primary_result().
        result = state.primary_result()
        if result is None:
            log.error("verifier_no_primary")
            return {"status": IncidentStatus.FAILED}
        expected = result.expected_outcome
        readings = call_tool(sensor_server, "read_sensors")
        current = float(readings[expected.target_metric])

        verdict = self._check(expected, current)
        met = verdict.verdict == "met"
        # "missed" with budget left → PLANNING (the router loops back to replan); met, or
        # missed-and-out-of-budget → a terminal verdict that ends the incident.
        if met:
            new_status = IncidentStatus.CLOSED
        elif replans_left(state.replan_count):
            new_status = IncidentStatus.PLANNING
        else:
            new_status = IncidentStatus.FAILED
        terminal = new_status is not IncidentStatus.PLANNING

        call_tool(
            ticket_server,
            "update_incident",
            incident_id=state.incident_id,
            status=new_status.value,
            verdict=verdict.verdict,
            delta=verdict.delta,
        )
        log.info(
            "verifier_verdict",
            verdict=verdict.verdict,
            delta=verdict.delta,
            current=current,
            status=new_status.value,
        )
        # Trajectory → Episodic Memory only on a TERMINAL verdict. Hard Constraint #3: the
        # write goes through the memory module (with audit log), not an inline upsert here.
        # A retry's interim miss is NOT the incident's outcome — the eventual terminal
        # trajectory records what finally happened; interim misses live in action_log /
        # LangFuse. verdict/new_status are passed in because they are not yet in `state`
        # (LangGraph merges this node's return only after the node finishes).
        if terminal:
            save_trajectory(state, verdict=verdict, status=new_status)
        return {"verifier_verdict": verdict, "status": new_status}

    def _check(self, expected: ExpectedOutcome, current: float) -> VerifierVerdict:
        prompt = self._template.safe_substitute(
            expected=expected.model_dump_json(), current=str(current)
        )
        try:
            raw = self.router.complete(
                "verifier.check",
                [{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            return VerifierVerdict.model_validate_json(raw)
        except (RouterExhausted, ValidationError, ValueError) as exc:
            log.warning("verifier_llm_fallback", error=str(exc))
            # Phase 1 CO2 upper-bound semantics: met when current <= target.
            delta = round(current - expected.target_value, 1)
            return VerifierVerdict(
                verdict="met" if current <= expected.target_value else "missed", delta=delta
            )
