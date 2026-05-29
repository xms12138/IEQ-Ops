"""ReflectionGraph — the weekly cold-path consolidation graph.

    load_episodes → (route_by_type: Send one branch per non-empty incident type)
                  → reflect [fan-out, REASONING] → consolidate → END

Triggered Sunday 03:00 (cron — wired in Phase 5 ops/deployment; Phase 3 ships the
graph + a manual runner, ops/scripts/run_reflection.py). It reads a window of
closed episodic trajectories, fans out ONE branch per incident type (airquality /
thermal / lighting / acoustic) so each Reflector call sees a bounded slice and
stays inside the context window (ops/llm_routing.md #7 token hazard), then a single
`consolidate` node persists the merged drafts — semantic facts via
memory.semantic.save_facts, SOP drafts via memory.procedural.queue_sop (PENDING:
human sign-off gates activation, Hard Constraint #8).

Independent from MainIncidentGraph: its own state (ReflectionState), no shared
in-memory state, no checkpointer (a weekly batch has nothing to resume — unlike the
15-min suspend on the hot path). The fan-out reuses the project's dispatch pattern:
a Send carries one type's cases as the branch payload (NOT parent state), and the
operator.add reducers merge the concurrent draft writes safely.

Reflector is MANDATORY cloud deepseek-v4-pro (Hard Constraint #12); the routing is
in core/router.py (reflector.semantic / reflector.procedural → REASONING). The
consolidate node carries no LLM (snake_case infra naming, CLAUDE.md).
"""

from __future__ import annotations

import operator
from collections.abc import Callable
from functools import lru_cache
from typing import Annotated, Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from pydantic import BaseModel, Field

from agents.reflector import ReflectorAgent
from core.logging import get_logger
from core.state import SENSOR_DOMAIN
from memory.episodic import EpisodicCase, list_trajectories
from memory.procedural import SOPDraft, queue_sop
from memory.semantic import SemanticFactDraft, save_facts

log = get_logger("reflection")

# The four incident types reflection chunks by (== specialist domains).
_INCIDENT_TYPES = ("airquality", "thermal", "lighting", "acoustic")


class ReflectionState(BaseModel):
    """Isolated state for the weekly ReflectionGraph (not persisted)."""

    week: str  # ISO week tag, e.g. "2026-W22" — stamps minted fact/SOP ids
    since: str | None = None  # ISO-8601 window bounds for list_trajectories
    until: str | None = None

    # load_episodes → route_by_type: cases bucketed by type, fed to the fan-out via
    # Send. Lives in (non-persisted) state only to bridge the node→edge handoff.
    episodes_by_type: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    n_episodes: int = 0

    # fan-out reflect accumulators — concurrent branch writes → add reducer.
    fact_drafts: Annotated[list[SemanticFactDraft], operator.add] = Field(default_factory=list)
    sop_drafts: Annotated[list[SOPDraft], operator.add] = Field(default_factory=list)

    # consolidate outputs (audit / runner display).
    saved_fact_ids: list[str] = Field(default_factory=list)
    queued_sop_ids: list[str] = Field(default_factory=list)


@lru_cache(maxsize=1)
def _agent() -> ReflectorAgent:
    """One shared ReflectorAgent (loads both prompts + a Router). LangGraph runs the
    fan-out branches sequentially in a superstep, so a single instance is safe."""
    return ReflectorAgent()


def _type_of(case: EpisodicCase) -> str:
    """Incident type = the specialist domain of the anomaly's sensor."""
    return SENSOR_DOMAIN.get(case.sensor, "airquality")


def load_episodes(state: ReflectionState) -> dict[str, Any]:
    """Read the window's closed trajectories from episodic memory and bucket them
    by incident type. The buckets (not whole state) seed the per-type fan-out."""
    cases = list_trajectories(since=state.since, until=state.until)
    buckets: dict[str, list[dict[str, Any]]] = {}
    for c in cases:
        buckets.setdefault(_type_of(c), []).append(c.model_dump())
    log.info(
        "reflection_load",
        week=state.week,
        n=len(cases),
        by_type={k: len(v) for k, v in buckets.items()},
    )
    return {"episodes_by_type": buckets, "n_episodes": len(cases)}


def route_by_type(state: ReflectionState) -> list[Send] | str:
    """Fan out one `reflect` branch per non-empty incident type. Each Send carries
    that type's cases as an isolated branch payload (like dispatch). Nothing to
    reflect → straight to consolidate (which no-ops)."""
    sends = [
        Send("reflect", {"incident_type": t, "cases": cases, "week": state.week})
        for t, cases in state.episodes_by_type.items()
        if cases
    ]
    if not sends:
        log.info("reflection_nothing_to_do", week=state.week)
        return "consolidate"
    return sends


def reflect(payload: dict[str, Any]) -> dict[str, Any]:
    """One incident type's reflection branch (fan-out target). Receives the Send
    payload — incident_type + that type's cases — NOT the parent state. Produces
    fact + SOP drafts (REASONING-tier cloud, Hard Constraint #12); the add reducers
    merge them across the parallel branches into ReflectionState."""
    incident_type = str(payload["incident_type"])
    cases = [EpisodicCase.model_validate(c) for c in payload["cases"]]
    agent = _agent()
    facts = agent.reflect_semantic(incident_type, cases)
    sops = agent.reflect_procedural(incident_type, cases)
    log.info("reflect_branch", incident_type=incident_type, n_facts=len(facts), n_sops=len(sops))
    return {"fact_drafts": facts, "sop_drafts": sops}


def consolidate(state: ReflectionState) -> dict[str, Any]:
    """Final summarisation pass: persist the merged drafts (Hard Constraint #3 —
    through the memory modules, with audit logs). Semantic facts → save_facts; SOP
    drafts → queue_sop (PENDING; human sign-off gates activation). Runs serially,
    so the SF/SOP sequence ids are assigned without a concurrent-id race."""
    saved = save_facts(state.fact_drafts, week=state.week)
    queued = [queue_sop(d, week=state.week) for d in state.sop_drafts]
    log.info(
        "reflection_consolidate", week=state.week, n_facts=len(saved), n_pending_sops=len(queued)
    )
    return {"saved_fact_ids": saved, "queued_sop_ids": queued}


# Node-wrapper plumbing mirrors core/graph.py: `wrap(node_fn, name)` lets the runner
# attach a LangFuse @observe span per node without coupling this module to a tracing
# lib (default identity). It also unifies the node signatures — load/consolidate take
# ReflectionState, `reflect` takes a Send payload dict — into the one Any-input _Node
# the typed StateGraph accepts.
_Node = Callable[[Any], dict[str, Any]]
_NodeWrapper = Callable[[_Node, str], Any]


def _identity(fn: _Node, name: str) -> _Node:
    return fn


def build_reflection_graph(wrap: _NodeWrapper = _identity) -> Any:
    """Compile the ReflectionGraph (no checkpointer — a weekly batch has nothing to
    resume). Compiled by the runner per pass, not held as a module global."""
    g: StateGraph[ReflectionState] = StateGraph(ReflectionState)
    g.add_node("load_episodes", wrap(load_episodes, "load_episodes"))
    g.add_node("reflect", wrap(reflect, "reflect"))
    g.add_node("consolidate", wrap(consolidate, "consolidate"))
    g.add_edge(START, "load_episodes")
    g.add_conditional_edges("load_episodes", route_by_type, ["reflect", "consolidate"])
    g.add_edge("reflect", "consolidate")
    g.add_edge("consolidate", END)
    return g.compile()
