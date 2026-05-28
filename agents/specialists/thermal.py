"""ThermalExpert — thin wrapper over SpecialistSubgraph (domain="thermal").

Same shape as AirQualityExpert; only the domain differs (selects the thermal RAG
slice). Phase 2: wired as a fan-out DIAGNOSIS target so a DAG can dispatch a
thermal side-effect subtask (e.g. ventilation's impact on comfort). A thermal
ACTUATOR / action branch is still Phase 5 — for now only airquality acts.
"""

from __future__ import annotations

from typing import Any

from agents.specialists.builder import run_specialist


class ThermalExpert:
    DOMAIN = "thermal"

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return run_specialist(payload, self.DOMAIN)
