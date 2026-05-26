"""AirQualityExpert — Phase 1 STUB.

Phase 1 does not implement the 5-node Agentic RAG loop. This stub returns a
fixed diagnosis carrying the mandatory ExpectedOutcome schema (Hard Constraint
#13) so the downstream autonomy gate, action, and Verifier can run end to end.

Phase 2 replaces this file with a thin wrapper that invokes the shared
SpecialistSubgraph (agents/specialists/builder.py) with domain="airquality";
the diagnosis and expected_outcome will then come from `generate`, not a
hard-coded string.
"""

from __future__ import annotations

from typing import Any

from core.logging import get_logger
from core.state import ExpectedOutcome, IncidentStatus, MainIncidentState, SpecialistResult

log = get_logger("airquality")


class AirQualityExpert:
    def run(self, state: MainIncidentState) -> dict[str, Any]:
        plan = state.current_plan
        assert plan is not None and plan.subtasks, "specialist reached without a plan"
        subtask = plan.subtasks[0]  # Phase 1: single subtask
        result = SpecialistResult(
            subtask_id=subtask.subtask_id,
            diagnosis=(
                "CO2 is elevated because the occupancy load exceeds the current "
                "fresh-air supply. Increasing ventilation will bring it back within "
                "the ASHRAE 62.1 guideline."
            ),
            expected_outcome=ExpectedOutcome(
                target_metric="co2", target_value=900.0, target_time_min=15
            ),
        )
        log.info("airquality_diagnosis", subtask_id=subtask.subtask_id)
        return {
            "subtask_results": {subtask.subtask_id: result},
            "status": IncidentStatus.ACTING,
        }
