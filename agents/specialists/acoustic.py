"""AcousticExpert — thin wrapper over SpecialistSubgraph (domain="acoustic").

Same shape as AirQualityExpert; only the domain differs (selects the acoustic RAG
slice). Phase 2: wired as a fan-out DIAGNOSIS target so the planner can dispatch
an acoustic subtask. An acoustic ACTUATOR / action branch is still Phase 5 — for
now only airquality acts.
"""

from __future__ import annotations

from typing import Any

from agents.specialists.builder import run_specialist


class AcousticExpert:
    DOMAIN = "acoustic"

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return run_specialist(payload, self.DOMAIN)
