"""VerifierAgent — node `verifier.check` (ops/llm_routing.md #6).

Runs 15 (simulated) minutes after the action. Reads the target metric again and
checks it against the specialist's declared ExpectedOutcome (Hard Constraint #13)
— a pure numeric comparison, which is exactly why this can run on the LOCAL tier
(Qwen3-8B in prod; dev override → deepseek-v4-flash). Closes the incident on
"met", marks it failed on "missed" (Phase 2 will route "missed" to replan).

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
)
from mcp_servers.client import call_tool
from mcp_servers.sensor.server import mcp as sensor_server
from mcp_servers.ticket.server import mcp as ticket_server

log = get_logger("verifier")


class VerifierAgent:
    def __init__(self, router: Router | None = None) -> None:
        self.router = router or Router()
        self._template = load_prompt("verifier")

    def run(self, state: MainIncidentState) -> dict[str, Any]:
        result = next(iter(state.subtask_results.values()))
        expected = result.expected_outcome
        readings = call_tool(sensor_server, "read_sensors")
        current = float(readings[expected.target_metric])

        verdict = self._check(expected, current)
        met = verdict.verdict == "met"
        new_status = IncidentStatus.CLOSED if met else IncidentStatus.FAILED
        call_tool(
            ticket_server,
            "update_incident",
            incident_id=state.incident_id,
            status=new_status.value,
            verdict=verdict.verdict,
            delta=verdict.delta,
        )
        log.info("verifier_verdict", verdict=verdict.verdict, delta=verdict.delta, current=current)
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
