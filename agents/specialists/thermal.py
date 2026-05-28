"""ThermalExpert — thin wrapper over SpecialistSubgraph (domain="thermal").

Same shape as AirQualityExpert; only the domain differs (selects the thermal RAG
slice + tool subset). Built in Phase 2 alongside the subgraph; wired into the
parent graph in Phase 5 when a thermal actuator + action branch exist.
"""

from __future__ import annotations

from typing import Any

from agents.specialists.builder import run_specialist
from core.state import MainIncidentState


class ThermalExpert:
    DOMAIN = "thermal"

    def run(self, state: MainIncidentState) -> dict[str, Any]:
        return run_specialist(state, self.DOMAIN)
