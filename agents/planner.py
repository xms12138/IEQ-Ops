"""PlannerAgent — node `planner.plan` (ops/llm_routing.md #3).

Phase 1 is deliberately minimal: produce ONE subtask routed to the right domain
specialist, not a full ReWOO DAG (that is Phase 2). Routing: REASONING tier
(deepseek-v4-pro).

Memory retrieval is done INLINE here, not as a LangGraph node (CLAUDE.md:
"MemoryAgent is not a LangGraph node"). Phase 1 it is a placeholder returning no
similar cases; Phase 3 swaps in memory/episodic.py::retrieve_similar().
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from agents.prompt_loader import load_prompt
from core.logging import get_logger
from core.router import Router, RouterExhausted
from core.state import IncidentStatus, MainIncidentState, Plan, Subtask

log = get_logger("planner")

# sensor → specialist domain (used by the deterministic fallback plan)
_SENSOR_DOMAIN = {
    "co2": "airquality",
    "temperature": "thermal",
    "humidity": "thermal",
    "lux": "lighting",
    "noise_db": "acoustic",
}


class PlannerAgent:
    def __init__(self, router: Router | None = None) -> None:
        self.router = router or Router()
        self._template = load_prompt("planner")

    def run(self, state: MainIncidentState) -> dict[str, Any]:
        similar_cases = self._retrieve_similar(state)  # inline placeholder (Phase 3)
        plan = self._plan(state, similar_cases)
        log.info("planner_plan", subtasks=[s.subtask_id for s in plan.subtasks])
        return {
            "current_plan": plan,
            "similar_cases": similar_cases,
            "status": IncidentStatus.DIAGNOSING,
        }

    def _retrieve_similar(self, state: MainIncidentState) -> list[str]:
        # Phase 3: memory.episodic.retrieve_similar(state.anomaly) → top-k incident ids
        return []

    def _plan(self, state: MainIncidentState, similar_cases: list[str]) -> Plan:
        anomaly = state.anomaly
        assert anomaly is not None, "planner reached without an anomaly"
        prompt = self._template.safe_substitute(
            anomaly=anomaly.model_dump_json(),
            similar_cases=str(similar_cases),
        )
        try:
            raw = self.router.complete(
                "planner.plan",
                [{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            plan = Plan.model_validate_json(raw)
            if not plan.subtasks:
                raise ValueError("planner returned an empty plan")
            return plan
        except (RouterExhausted, ValidationError, ValueError) as exc:
            log.warning("planner_llm_fallback", error=str(exc))
            return self._fallback_plan(anomaly.sensor, anomaly.rule_violated)

    def _fallback_plan(self, sensor: str, rule_violated: str) -> Plan:
        domain = _SENSOR_DOMAIN.get(sensor, "airquality")
        return Plan(
            subtasks=[
                Subtask(
                    subtask_id="S1",
                    domain=domain,
                    goal=f"Diagnose the {sensor} violation: {rule_violated}",
                )
            ]
        )
