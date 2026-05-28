"""AirQualityExpert — thin wrapper over SpecialistSubgraph (domain="airquality").

Phase 2: this is a fan-out target node. The dispatch loop sends it a single
subtask via `Send("airquality", {"subtask": ...})`, so `run` receives the Send
payload (NOT the parent state) and delegates to the shared 5-node Agentic RAG
subgraph. All RAG intermediate state stays inside the subgraph (🔴 risk #2).
"""

from __future__ import annotations

from typing import Any

from agents.specialists.builder import run_specialist


class AirQualityExpert:
    DOMAIN = "airquality"

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return run_specialist(payload, self.DOMAIN)
