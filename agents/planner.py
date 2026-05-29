"""PlannerAgent — node `planner.plan` (ops/llm_routing.md #3).

Phase 2: produce a real Plan-and-Execute + ReWOO DAG — a primary diagnosis
subtask plus any cross-domain side-effect subtasks that depend on it (via
`#{id}.diagnosis` placeholders, hydrated downstream). Routing: REASONING tier
(deepseek-v4-pro), temperature 0 so the plan shape is reproducible while thinking
stays on (the DAG decomposition is the reasoning task — unlike the specialist's
JSON/short-string nodes, planner keeps thinking enabled).

Phase 3: memory retrieval is now LIVE. retrieve_similar() (memory/episodic.py) is
called INLINE here, not as a LangGraph node (CLAUDE.md: "MemoryAgent is not a
LangGraph node"). The recalled trajectories — each carrying its diagnosis, action,
and met/missed verdict — are folded into the planner prompt (v3) as advisory
context; only the incident ids go to state.similar_cases (audit/trace).
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from agents.prompt_loader import load_prompt
from core.logging import get_logger
from core.router import Router, RouterExhausted
from core.state import SENSOR_DOMAIN, IncidentStatus, MainIncidentState, Plan, Subtask
from memory.episodic import EpisodicCase, retrieve_similar

log = get_logger("planner")


def _format_cases(cases: list[EpisodicCase]) -> str:
    """Render recalled trajectories as compact lines for the planner prompt. An
    empty recall (cold start) becomes an explicit '(none)' so the prompt reads
    cleanly and the planner falls back to anomaly-only planning."""
    if not cases:
        return "(none)"
    lines: list[str] = []
    for c in cases:
        outcome = "resolved" if c.verdict == "met" else "FAILED"
        lines.append(
            f"- [{c.incident_id}] {c.sensor}={c.value} ({c.rule_violated}) "
            f"→ diagnosis: {c.diagnosis} | action: {c.action_taken or 'n/a'} "
            f"→ {outcome} (target {c.target_metric}≤{c.target_value}; sim={c.score:.2f})"
        )
    return "\n".join(lines)


class PlannerAgent:
    def __init__(self, router: Router | None = None) -> None:
        self.router = router or Router()
        self._template = load_prompt("planner", 3)

    def run(self, state: MainIncidentState) -> dict[str, Any]:
        cases = self._retrieve_similar(state)  # inline episodic recall (CLAUDE.md)
        plan = self._plan(state, cases)
        log.info(
            "planner_plan",
            subtasks=[s.subtask_id for s in plan.subtasks],
            recalled=[c.incident_id for c in cases],
        )
        return {
            "current_plan": plan,
            "similar_cases": [c.incident_id for c in cases],  # ids only → state
            "status": IncidentStatus.DIAGNOSING,
        }

    def _retrieve_similar(self, state: MainIncidentState) -> list[EpisodicCase]:
        a = state.anomaly
        if a is None:
            return []
        return retrieve_similar(a.sensor, a.value, a.rule_violated)

    def _plan(self, state: MainIncidentState, cases: list[EpisodicCase]) -> Plan:
        anomaly = state.anomaly
        assert anomaly is not None, "planner reached without an anomaly"
        prompt = self._template.safe_substitute(
            anomaly=anomaly.model_dump_json(),
            similar_cases=_format_cases(cases),
        )
        try:
            raw = self.router.complete(
                "planner.plan",
                [{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.0,
            )
            plan = Plan.model_validate_json(raw)
            if not plan.subtasks:
                raise ValueError("planner returned an empty plan")
            return plan
        except (RouterExhausted, ValidationError, ValueError) as exc:
            log.warning("planner_llm_fallback", error=str(exc))
            return self._fallback_plan(anomaly.sensor, anomaly.rule_violated)

    def _fallback_plan(self, sensor: str, rule_violated: str) -> Plan:
        domain = SENSOR_DOMAIN.get(sensor, "airquality")
        return Plan(
            subtasks=[
                Subtask(
                    subtask_id="S1",
                    domain=domain,
                    goal=f"Diagnose the {sensor} violation: {rule_violated}",
                )
            ]
        )
