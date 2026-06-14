"""CriticAgent — node `critic.validate` (ops/llm_routing.md #5).

Validates the actionable (primary) specialist diagnosis before the autonomy gate
lets it drive an actuator. Runs once after the subtask DAG completes.

PLAN B (Phase 2 decision, 2026-05-28). The critic does NOT trace claims back to
the retrieved standard excerpts. Subgraph state isolation (🔴 Phase 2 risk #2)
deliberately keeps `retrieved_chunks` out of the parent checkpoint, so the parent
critic cannot see them — numeric trace-back against source text is impossible
here by design. Instead it validates two things it CAN see:

  1. expected_outcome plausibility — a DETERMINISTIC numeric floor (no LLM): the
     target_metric is known and target_value sits in a physically sane range for
     it, and target_time_min is a sane window. An absurd target (e.g. co2 → 5 ppm
     in 1 min) is blocked regardless of what the LLM says.
  2. internal coherence + outcome-to-diagnosis fit — the `critic.validate` LLM
     call (routed LOCAL → flash under override B). A deterministic
     plausibility-only verdict backs it up so an LLM outage never deadlocks the
     loop.

On disapproval the routing depends on the primary domain's action tier. A domain the
system would auto-actuate (Tier 1/2) is failed (status FAILED, ticket patched) and the
graph routes to END WITHOUT acting — never actuate on an incoherent or implausible
diagnosis. A human-only domain (Tier 3, no actuator) instead ESCALATES to the human at
the autonomy gate (status AWAITING_APPROVAL): there is no autonomous action to suppress,
so the incident is reported for human resolution, not failed. Routing a Tier 1/2
disapproval to *replan* is deferred to Phase 3 (it pairs with episodic memory and the
subtask_results reset a clean replan needs).
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from agents.prompt_loader import load_prompt
from core.logging import get_logger
from core.router import Router, RouterExhausted
from core.state import (
    AutonomyTier,
    CriticVerdict,
    IncidentStatus,
    MainIncidentState,
    SpecialistResult,
    replans_left,
    tier_for_sensor,
)
from mcp_servers.client import call_tool
from mcp_servers.ticket.server import mcp as ticket_server

log = get_logger("critic")

# Physically sane bounds per sensor metric — a hard floor, NOT a comfort target.
# These reject an absurd expected_outcome (co2 → 5 ppm) without judging whether a
# plausible target is *optimal*; that is the specialist's grounded call.
_PLAUSIBLE_RANGE: dict[str, tuple[float, float]] = {
    "co2": (350.0, 5000.0),  # ppm — outdoor baseline ≈ 400, far above any indoor cap
    "temperature": (10.0, 40.0),  # °C operative
    "humidity": (10.0, 95.0),  # %RH
    "lux": (20.0, 3000.0),  # illuminance
    "noise_db": (25.0, 95.0),  # dB(A)
}
# A corrective action that should take effect between 1 min and 4 h.
_MIN_TARGET_MINUTES, _MAX_TARGET_MINUTES = 1, 240


class CriticAgent:
    def __init__(self, router: Router | None = None) -> None:
        self.router = router or Router()
        self._template = load_prompt("critic")

    def run(self, state: MainIncidentState) -> dict[str, Any]:
        if state.failed_subtasks:
            # An advisory cross-domain subtask failed; the primary may still be
            # actionable. Log it; the verdict is decided on the primary below.
            log.warning("critic_partial_failure", failed=sorted(state.failed_subtasks))

        primary = state.primary_result()
        if primary is None:
            verdict = CriticVerdict(approved=False, unsupported_claims=["no actionable diagnosis"])
            return self._fail(state, verdict)

        verdict = self._validate(primary, state)
        if not verdict.approved:
            log.warning("critic_disapproved", claims=verdict.unsupported_claims)
            return self._disapprove(state, verdict)
        log.info("critic_approved", subtask_id=primary.subtask_id)
        return {"critic_verdict": verdict, "status": IncidentStatus.ACTING}

    def _fail(self, state: MainIncidentState, verdict: CriticVerdict) -> dict[str, Any]:
        """Persist the terminal failure to the ticket so it is auditable, then let
        the conditional edge route to END (no action on a rejected diagnosis)."""
        if state.incident_id is not None:
            call_tool(
                ticket_server,
                "update_incident",
                incident_id=state.incident_id,
                status=IncidentStatus.FAILED.value,
            )
        return {"critic_verdict": verdict, "status": IncidentStatus.FAILED}

    def _disapprove(self, state: MainIncidentState, verdict: CriticVerdict) -> dict[str, Any]:
        """Route a disapproved diagnosis by the primary domain's action tier. A
        human-only domain (Tier 3, no actuator) has no autonomous action to suppress,
        so the rejection ESCALATES to the human at the autonomy gate (status
        AWAITING_APPROVAL) — the incident is reported, not failed. A domain the system
        would auto-actuate (Tier 1/2) loops back to the planner for a fresh diagnosis
        while replan budget remains (status PLANNING, no ticket FAILED write — the
        incident is being retried, not failed); only once the budget is spent is it
        failed. Either way: never act on a rejected diagnosis. The router
        (_route_after_critic) reads the SAME replans_left() so its edge matches."""
        sensor = state.anomaly.sensor if state.anomaly else None
        if tier_for_sensor(sensor) is AutonomyTier.APPROVE:
            log.info("critic_escalate_human", sensor=sensor)
            if state.incident_id is not None:
                call_tool(
                    ticket_server,
                    "update_incident",
                    incident_id=state.incident_id,
                    status=IncidentStatus.AWAITING_APPROVAL.value,
                )
            return {"critic_verdict": verdict, "status": IncidentStatus.AWAITING_APPROVAL}
        if replans_left(state.replan_count):
            log.info("critic_replan", sensor=sensor, attempt=state.replan_count + 1)
            return {"critic_verdict": verdict, "status": IncidentStatus.PLANNING}
        return self._fail(state, verdict)

    def _validate(self, result: SpecialistResult, state: MainIncidentState) -> CriticVerdict:
        # 1. Deterministic numeric floor — a hard reject the LLM cannot override.
        floor_flags = self._plausibility_flags(result)

        # 2. LLM coherence + outcome-to-diagnosis fit.
        prompt = self._template.safe_substitute(
            diagnosis=result.diagnosis,
            expected_outcome=result.expected_outcome.model_dump_json(),
            anomaly=state.anomaly.model_dump_json() if state.anomaly else "{}",
        )
        try:
            raw = self.router.complete(
                "critic.validate",
                [{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.0,
            )
            llm = CriticVerdict.model_validate_json(raw)
        except (RouterExhausted, ValidationError, ValueError) as exc:
            # Numeric floor still protects against unsafe actuation; skip the
            # coherence judgement rather than deadlock the loop (verifier-style).
            log.warning("critic_llm_fallback", error=str(exc))
            return CriticVerdict(approved=not floor_flags, unsupported_claims=floor_flags)

        claims = floor_flags + llm.unsupported_claims
        return CriticVerdict(approved=llm.approved and not floor_flags, unsupported_claims=claims)

    @staticmethod
    def _plausibility_flags(result: SpecialistResult) -> list[str]:
        eo = result.expected_outcome
        flags: list[str] = []
        bounds = _PLAUSIBLE_RANGE.get(eo.target_metric)
        if bounds is None:
            flags.append(f"unknown target_metric {eo.target_metric!r}")
        else:
            lo, hi = bounds
            if not lo <= eo.target_value <= hi:
                flags.append(
                    f"target_value {eo.target_value} for {eo.target_metric} "
                    f"outside plausible [{lo}, {hi}]"
                )
        if not _MIN_TARGET_MINUTES <= eo.target_time_min <= _MAX_TARGET_MINUTES:
            flags.append(
                f"target_time_min {eo.target_time_min} outside sane "
                f"[{_MIN_TARGET_MINUTES}, {_MAX_TARGET_MINUTES}] minutes"
            )
        return flags
