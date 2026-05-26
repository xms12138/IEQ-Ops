"""MainIncidentGraph — the Phase 1 hot-path state machine.

Node order:
    monitor → (anomaly?) → planner → dispatch → airquality → critic
            → autonomy_gate → action → ⟨suspend⟩ → verifier → END

The suspend between `action` and `verifier` is `interrupt_before=["verifier"]`
at compile time: the graph runs up to the verifier, checkpoints to Postgres, and
stops. An external trigger (cron in prod, ops/scripts/run_incident.py in dev)
resumes it 15 minutes later with the SAME thread_id, which is what must survive a
process restart (Phase 1 risk #1). Compilation (with the checkpointer) is done by
the caller inside open_checkpointer(); this module only builds the topology.

Infra nodes here (dispatch / critic / autonomy_gate / action) are snake_case and
carry no LLM (CLAUDE.md naming). The three LLM nodes live in agents/. critic is a
Phase 1 pass-through placeholder; it becomes claim-classification in Phase 2.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langgraph.graph import END, StateGraph
from langgraph.types import interrupt

from agents.monitor import MonitorAgent
from agents.planner import PlannerAgent
from agents.specialists.airquality import AirQualityExpert
from agents.verifier import VerifierAgent
from core.logging import get_logger
from core.state import AutonomyTier, CriticVerdict, IncidentStatus, MainIncidentState
from mcp_servers.actuator.server import mcp as actuator_server
from mcp_servers.client import call_tool
from mcp_servers.ticket.server import mcp as ticket_server

log = get_logger("graph")

# Compile-time suspend point — the 15-min wait that must survive a restart.
INTERRUPT_BEFORE = ["verifier"]

# Reversibility + occupant impact set the tier. Ventilation is reversible and
# low-impact → Tier 1. Unknown domains fall to the safest tier (require approval).
_TIER_BY_DOMAIN: dict[str, AutonomyTier] = {
    "airquality": AutonomyTier.AUTO,
}


# ── infra nodes (no LLM) ──────────────────────────────────────────────────────


def dispatch(state: MainIncidentState) -> dict[str, Any]:
    """Routing-only node. Phase 1 has one subtask; Phase 2 fans out to parallel
    specialists. The actual branch is chosen by the conditional edge below."""
    assert state.current_plan is not None
    domain = state.current_plan.subtasks[0].domain
    log.info("dispatch", domain=domain)
    return {}


def critic(state: MainIncidentState) -> dict[str, Any]:
    """Phase 1 placeholder — approves everything. Phase 2: classify each claim
    (numeric/direct-quote → local; inductive → escalate V4-Flash) per #5."""
    return {"critic_verdict": CriticVerdict(approved=True)}


def autonomy_gate(state: MainIncidentState) -> dict[str, Any]:
    """Tier the action; Tier 3 blocks on interrupt() until a human approves
    (Hard Constraint #2 — never bypassed, even in dev). Phase 1's airquality
    path is Tier 1, so the interrupt branch is structural, not exercised yet."""
    assert state.current_plan is not None
    domain = state.current_plan.subtasks[0].domain
    tier = _TIER_BY_DOMAIN.get(domain, AutonomyTier.APPROVE)
    log.info("autonomy_gate", domain=domain, tier=int(tier))
    if tier is AutonomyTier.APPROVE:
        decision = interrupt({"reason": "Tier 3 action requires human approval", "domain": domain})
        if not (isinstance(decision, dict) and decision.get("approved") is True):
            log.info("autonomy_gate_rejected", domain=domain)
            return {"autonomy_tier": tier, "status": IncidentStatus.FAILED}
    return {"autonomy_tier": tier}


def action(state: MainIncidentState) -> dict[str, Any]:
    """Execute via mcp-actuator-server. Phase 1 maps an airquality incident to
    'ventilation high'; Phase 2 derives the action from the specialist's
    proposed intervention instead of hard-coding it here."""
    result = call_tool(
        actuator_server,
        "set_ventilation",
        level="high",
        reason=f"incident {state.incident_id}: lower CO2 below target",
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


def _route_to_specialist(state: MainIncidentState) -> str:
    """Pick the specialist by the (single, Phase 1) subtask domain. Only
    airquality is implemented in Phase 1; anything else is a planner bug, so we
    log and fall back to airquality rather than dead-ending the incident."""
    assert state.current_plan is not None
    domain = state.current_plan.subtasks[0].domain
    if domain != "airquality":
        log.warning("dispatch_unimplemented_domain", domain=domain, fallback="airquality")
    return "airquality"


# ── graph assembly ────────────────────────────────────────────────────────────


_Node = Callable[[MainIncidentState], dict[str, Any]]
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
    builder.add_node("dispatch", wrap(dispatch, "dispatch"))
    builder.add_node("airquality", wrap(AirQualityExpert().run, "airquality"))
    builder.add_node("critic", wrap(critic, "critic"))
    builder.add_node("autonomy_gate", wrap(autonomy_gate, "autonomy_gate"))
    builder.add_node("action", wrap(action, "action"))
    builder.add_node("verifier", wrap(VerifierAgent().run, "verifier"))

    builder.set_entry_point("monitor")
    builder.add_conditional_edges("monitor", _route_after_monitor, {"planner": "planner", END: END})
    builder.add_edge("planner", "dispatch")
    builder.add_conditional_edges("dispatch", _route_to_specialist, {"airquality": "airquality"})
    builder.add_edge("airquality", "critic")
    builder.add_edge("critic", "autonomy_gate")
    builder.add_edge("autonomy_gate", "action")
    builder.add_edge("action", "verifier")
    builder.add_edge("verifier", END)

    return builder
