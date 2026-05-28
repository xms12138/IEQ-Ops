"""AirQualityExpert — thin wrapper over SpecialistSubgraph (domain="airquality").

Phase 1 was a hard-coded stub. Phase 2: invoke the shared 5-node Agentic RAG
subgraph and lift only `final_diagnosis` back into the parent graph. All the RAG
intermediate state stays inside the subgraph (🔴 risk #2). The class keeps its
`run(state) -> dict` shape so core/graph.py wires it unchanged.
"""

from __future__ import annotations

from typing import Any

from agents.specialists.builder import run_specialist
from core.state import MainIncidentState


class AirQualityExpert:
    DOMAIN = "airquality"

    def run(self, state: MainIncidentState) -> dict[str, Any]:
        return run_specialist(state, self.DOMAIN)
