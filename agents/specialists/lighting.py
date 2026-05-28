"""LightingExpert — thin wrapper over SpecialistSubgraph (domain="lighting").

Same shape as AirQualityExpert; only the domain differs (selects the lighting RAG
slice). Phase 2: wired as a fan-out DIAGNOSIS target so the planner can dispatch
a lighting subtask. A lighting ACTUATOR / action branch is still Phase 5 — for
now only airquality acts.
"""

from __future__ import annotations

from typing import Any

from agents.specialists.builder import run_specialist


class LightingExpert:
    DOMAIN = "lighting"

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return run_specialist(payload, self.DOMAIN)
