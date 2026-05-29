"""MainIncidentGraph — the hot-path state machine.

Node order (Phase 2 — ReWOO DAG fan-out replaces Phase 1's single specialist):
    monitor → (anomaly?) → planner
            → hydrate_placeholders → dispatch ⇄ {airquality|thermal|lighting|acoustic}
            → critic → autonomy_gate → action → ⟨suspend⟩ → verifier → END

The dispatch loop is a wave-based topological executor over the planner's subtask
DAG. Each pass:
  1. `hydrate_placeholders` resolves the ReWOO refs (`#{id}.diagnosis`) of every
     subtask whose dependencies have completed — "before the dependent runs".
  2. `dispatch`'s conditional edge fans out the READY wave as parallel
     `Send(domain, {"subtask": ...})` tasks; specialists with no mutual
     dependency run concurrently in one superstep.
  3. Each specialist loops back to `hydrate_placeholders`; the next wave's refs
     are now resolvable. When nothing is ready (all done, or the rest is blocked
     by a failed dependency) the edge routes to `critic`.
The merge/append reducers on `subtask_results` / `failed_subtasks` (core/state.py)
are what make the concurrent fan-out writes safe.

`critic` (CriticAgent, agents/critic.py) validates the primary diagnosis before
the autonomy gate: it approves → `autonomy_gate`, or disapproves → END without
acting (Plan B — it cannot see the subgraph's retrieved chunks, so it validates
coherence + expected_outcome plausibility, not source trace-back).

The suspend between `action` and `verifier` is `interrupt_before=["verifier"]` at
compile time: the graph runs the whole DAG + action, checkpoints to Postgres, and
stops; an external trigger resumes it 15 min later with the SAME thread_id
(Phase 1 risk #1). Compilation is done by the caller inside open_checkpointer();
this module only builds the topology.

Infra nodes here (hydrate_placeholders / dispatch / autonomy_gate / action) are
snake_case and carry no LLM (CLAUDE.md naming). `critic` is an LLM agent node
(CriticAgent) and lives in agents/critic.py.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from langgraph.graph import END, StateGraph
from langgraph.types import Send, interrupt

from agents.critic import CriticAgent
from agents.monitor import MonitorAgent
from agents.planner import PlannerAgent
from agents.specialists.acoustic import AcousticExpert
from agents.specialists.airquality import AirQualityExpert
from agents.specialists.lighting import LightingExpert
from agents.specialists.thermal import ThermalExpert
from agents.verifier import VerifierAgent
from core.logging import get_logger
from core.state import (
    SENSOR_DOMAIN,
    AutonomyTier,
    IncidentStatus,
    MainIncidentState,
    Plan,
    SpecialistResult,
    Subtask,
)
from mcp_servers.actuator.server import mcp as actuator_server
from mcp_servers.client import call_tool
from mcp_servers.ticket.server import mcp as ticket_server

log = get_logger("graph")

# Compile-time suspend point — the 15-min wait that must survive a restart.
INTERRUPT_BEFORE = ["verifier"]

# The four fan-out specialist node names (== domains). A planner-emitted domain
# outside this set is a bug; route_dispatch clamps it rather than Send-ing to a
# non-existent node.
_SPECIALIST_DOMAINS = ("airquality", "thermal", "lighting", "acoustic")

# Reversibility + occupant impact set the tier. Only airquality has an actuator
# in Phase 2 (ventilation: reversible, low-impact → Tier 1). Other domains have
# no action branch yet (Phase 5) and fall to the safest tier.
_TIER_BY_DOMAIN: dict[str, AutonomyTier] = {
    "airquality": AutonomyTier.AUTO,
}

# ReWOO placeholder: #{subtask_id}.{field} e.g. #S1.diagnosis (CLAUDE.md naming).
# Optional braces tolerate the #{S1}.diagnosis variant too: the planner LLM
# sometimes copies the {subtask_id} meta-notation literally, and an unhydrated
# dependency silently breaks ReWOO (the dependent specialist never sees the
# upstream diagnosis). Lenient parsing here is cheaper + safer than relying on
# prompt discipline to never drift.
_REWOO_REF = re.compile(r"#\{?(\w+)\}?\.(\w+)")


# ── DAG helpers ───────────────────────────────────────────────────────────────


def _ready_subtasks(state: MainIncidentState) -> list[Subtask]:
    """Subtasks not yet resolved whose dependencies have all SUCCEEDED. A failed
    dependency (in failed_subtasks but not subtask_results) leaves its dependents
    permanently un-ready, so the wave loop terminates instead of spinning."""
    plan = state.current_plan
    if plan is None:
        return []
    succeeded = set(state.subtask_results)
    resolved = succeeded | set(state.failed_subtasks)
    return [
        st
        for st in plan.subtasks
        if st.subtask_id not in resolved and set(st.depends_on) <= succeeded
    ]


def _hydrate_goal(goal: str, results: dict[str, SpecialistResult]) -> str:
    """Resolve every #{id}.{field} ref against completed subtask results. Refs to
    not-yet-completed subtasks are left verbatim (shouldn't happen once ready)."""

    def repl(m: re.Match[str]) -> str:
        sid, field = m.group(1), m.group(2)
        r = results.get(sid)
        if r is None:
            return m.group(0)
        if field == "diagnosis":
            return r.diagnosis
        if field in ("target_metric", "target_value", "target_time_min"):
            return str(getattr(r.expected_outcome, field))
        if field == "expected_outcome":
            return r.expected_outcome.model_dump_json()
        return m.group(0)

    return _REWOO_REF.sub(repl, goal)


# ── infra nodes (no LLM) ──────────────────────────────────────────────────────


def hydrate_placeholders(state: MainIncidentState) -> dict[str, Any]:
    """Fill `hydrated_goal` on every ready subtask by resolving its ReWOO refs
    against completed results — runs each wave, BEFORE dispatch fans the wave out.
    Only this node and planner write `current_plan`, and never in the same
    superstep as the parallel specialists, so no reducer is needed on it."""
    plan = state.current_plan
    if plan is None:
        return {}
    ready_ids = {st.subtask_id for st in _ready_subtasks(state)}
    if not ready_ids:
        return {}
    results = state.subtask_results
    new_subtasks: list[Subtask] = []
    for st in plan.subtasks:
        if st.subtask_id in ready_ids and st.hydrated_goal is None:
            hydrated = _hydrate_goal(st.goal, results)
            if hydrated != st.goal:
                log.info("hydrate", subtask_id=st.subtask_id, deps=st.depends_on)
            new_subtasks.append(st.model_copy(update={"hydrated_goal": hydrated}))
        else:
            new_subtasks.append(st)
    return {"current_plan": Plan(subtasks=new_subtasks)}


def dispatch(state: MainIncidentState) -> dict[str, Any]:
    """Fan-out point (the actual Sends are emitted by route_dispatch below).
    Logs wave progress; carries no state change."""
    ready = _ready_subtasks(state)
    log.info(
        "dispatch",
        wave=[st.subtask_id for st in ready],
        done=sorted(state.subtask_results),
        failed=sorted(state.failed_subtasks),
    )
    return {}


def autonomy_gate(state: MainIncidentState) -> dict[str, Any]:
    """Tier the action on the PRIMARY (actionable) subtask's domain; Tier 3 blocks
    on interrupt() until a human approves (Hard Constraint #2 — never bypassed).
    The primary domain follows the anomaly's sensor, not subtasks[0], so advisory
    cross-domain subtasks don't change the action tier."""
    if state.primary_result() is None:
        log.warning("autonomy_gate_no_primary")
        return {"status": IncidentStatus.FAILED}
    domain = (
        SENSOR_DOMAIN.get(state.anomaly.sensor, "airquality") if state.anomaly else "airquality"
    )
    tier = _TIER_BY_DOMAIN.get(domain, AutonomyTier.APPROVE)
    log.info("autonomy_gate", domain=domain, tier=int(tier))
    if tier is AutonomyTier.APPROVE:
        decision = interrupt({"reason": "Tier 3 action requires human approval", "domain": domain})
        if not (isinstance(decision, dict) and decision.get("approved") is True):
            log.info("autonomy_gate_rejected", domain=domain)
            return {"autonomy_tier": tier, "status": IncidentStatus.FAILED}
    return {"autonomy_tier": tier}


def action(state: MainIncidentState) -> dict[str, Any]:
    """Execute via mcp-actuator-server. Phase 2 still maps the airquality primary to
    ventilation; per-domain actuators are Phase 5. The verification target metric
    comes from the primary subtask's expected_outcome."""
    primary = state.primary_result()
    if primary is None:
        log.error("action_no_primary")
        return {"status": IncidentStatus.FAILED}
    metric = primary.expected_outcome.target_metric
    result = call_tool(
        actuator_server,
        "set_ventilation",
        level="high",
        reason=f"incident {state.incident_id}: lower {metric} below target",
    )
    action_desc = f"set_ventilation=high ({result['target_m3h']} m3/h)"
    call_tool(
        ticket_server,
        "update_incident",
        incident_id=state.incident_id,
        status=IncidentStatus.VERIFYING.value,
        action_taken=action_desc,
    )
    log.info("action_executed", action=action_desc)
    return {"action_taken": action_desc, "status": IncidentStatus.VERIFYING}


# ── conditional routing ───────────────────────────────────────────────────────


def _route_after_monitor(state: MainIncidentState) -> str:
    """No anomaly → nothing to do; otherwise start planning."""
    return "planner" if (state.anomaly is not None and state.anomaly.anomaly) else END


def route_dispatch(state: MainIncidentState) -> list[Send] | str:
    """Fan out the ready wave as parallel Sends to the domain specialist nodes;
    when nothing is ready (DAG complete, or remainder blocked by a failed dep),
    advance to critic. Each Send carries one subtask (with its hydrated goal)."""
    ready = _ready_subtasks(state)
    if not ready:
        return "critic"
    sends: list[Send] = []
    for st in ready:
        target = st.domain if st.domain in _SPECIALIST_DOMAINS else "airquality"
        if target != st.domain:
            log.warning("dispatch_unknown_domain", domain=st.domain, fallback=target)
        sends.append(Send(target, {"subtask": st.model_dump()}))
    return sends


def _route_after_critic(state: MainIncidentState) -> str:
    """Gate the action on the critic's verdict. Disapproval (incoherent or
    physically implausible primary diagnosis) ends the incident WITHOUT acting —
    CriticAgent has already marked it FAILED on the ticket. Phase 3 will route a
    disapproval to replan instead of END."""
    verdict = state.critic_verdict
    return "autonomy_gate" if verdict is not None and verdict.approved else END


# ── graph assembly ────────────────────────────────────────────────────────────


_Node = Callable[[Any], dict[str, Any]]
_NodeWrapper = Callable[[_Node, str], Any]


def _identity(fn: _Node, name: str) -> _Node:
    return fn


def build_main_graph(wrap: _NodeWrapper = _identity) -> StateGraph[MainIncidentState]:
    """Assemble the graph. `wrap(node_fn, node_name)` lets the caller wrap each
    node for observability (e.g. a LangFuse @observe span) WITHOUT coupling this
    module to any tracing library — the default is identity."""
    builder: StateGraph[MainIncidentState] = StateGraph(MainIncidentState)

    builder.add_node("monitor", wrap(MonitorAgent().run, "monitor"))
    builder.add_node("planner", wrap(PlannerAgent().run, "planner"))
    builder.add_node("hydrate_placeholders", wrap(hydrate_placeholders, "hydrate_placeholders"))
    builder.add_node("dispatch", wrap(dispatch, "dispatch"))
    builder.add_node("airquality", wrap(AirQualityExpert().run, "airquality"))
    builder.add_node("thermal", wrap(ThermalExpert().run, "thermal"))
    builder.add_node("lighting", wrap(LightingExpert().run, "lighting"))
    builder.add_node("acoustic", wrap(AcousticExpert().run, "acoustic"))
    builder.add_node("critic", wrap(CriticAgent().run, "critic"))
    builder.add_node("autonomy_gate", wrap(autonomy_gate, "autonomy_gate"))
    builder.add_node("action", wrap(action, "action"))
    builder.add_node("verifier", wrap(VerifierAgent().run, "verifier"))

    builder.set_entry_point("monitor")
    builder.add_conditional_edges("monitor", _route_after_monitor, {"planner": "planner", END: END})
    builder.add_edge("planner", "hydrate_placeholders")
    builder.add_edge("hydrate_placeholders", "dispatch")
    builder.add_conditional_edges("dispatch", route_dispatch, [*_SPECIALIST_DOMAINS, "critic"])
    # Every specialist loops back to hydrate the next wave (barrier: one hydrate
    # run per superstep regardless of how many specialists fanned out).
    for domain in _SPECIALIST_DOMAINS:
        builder.add_edge(domain, "hydrate_placeholders")
    builder.add_conditional_edges(
        "critic", _route_after_critic, {"autonomy_gate": "autonomy_gate", END: END}
    )
    builder.add_edge("autonomy_gate", "action")
    builder.add_edge("action", "verifier")
    builder.add_edge("verifier", END)

    return builder
