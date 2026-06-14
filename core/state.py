"""Global LangGraph state for MainIncidentGraph + the locked LLM-facing schemas.

Design notes
------------
* `MainIncidentState` is the parent graph's shared state, threaded through
  monitor → memory_retrieve → planner → dispatch → specialist → critic →
  autonomy_gate → action → verifier, and persisted to Postgres so the 15-min
  verification step survives restarts. Fields are snake_case (CLAUDE.md).
* Two schemas are LOCKED by hard constraints and use `extra="forbid"` so a model
  that invents extra fields fails validation instead of being silently accepted:
    - `AnomalyRecord`   (Hard Constraint #10) — MonitorAgent's only output shape.
    - `ExpectedOutcome` (Hard Constraint #13) — every Specialist answer carries one,
      which is exactly what lets the Verifier run on local Qwen3-8B.
* `SpecialistState` (the subgraph's isolated state) deliberately does NOT live
  here — it belongs with the subgraph (agents/specialists/) so its bulky
  intermediate fields (retrieved_chunks, grade_history, rewrite_count) never leak
  into this parent checkpoint. Only `subtask` enters and `final_diagnosis` returns.
* `Plan`/`Subtask` are minimal in Phase 0/1 (single subtask) and grow into the
  full ReWOO DAG in Phase 2. Placeholder ref format is `#{subtask_id}.{field}`.
"""

from __future__ import annotations

from enum import IntEnum, StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

# sensor → specialist domain. The "primary" subtask of an incident is the one
# whose domain matches the anomaly's sensor (e.g. a co2 anomaly → airquality):
# that is the actionable diagnosis the autonomy_gate / action / verifier operate
# on, while any dependent subtasks (e.g. thermal side-effect of ventilation) are
# advisory context. Shared by planner (fallback routing) and the parent graph.
SENSOR_DOMAIN: dict[str, str] = {
    "co2": "airquality",
    "temperature": "thermal",
    "humidity": "thermal",
    "lux": "lighting",
    "noise_db": "acoustic",
}


class _ResetResults(dict):  # type: ignore[type-arg]
    """Sentinel dict subclass: a reducer receiving one REPLACES the channel with its
    contents instead of merging. The replan node returns an empty one to clear the
    previous attempt's specialist results — a plain {} would merge to a no-op and the
    stale results would survive into the retry. It IS a dict, so the channel stays
    type-valid (the reducer normalises it back to a plain dict)."""


class _ResetList(list):  # type: ignore[type-arg]
    """Sentinel list subclass: tells the append reducer to REPLACE, not extend — the
    replan node clears failed_subtasks so a reused subtask_id is not seen as already
    resolved (which would leave the retry's subtasks permanently un-dispatched)."""


def _merge_results(
    a: dict[str, SpecialistResult], b: dict[str, SpecialistResult]
) -> dict[str, SpecialistResult]:
    """Reducer for subtask_results: parallel specialist fan-out (Send) writes this
    key concurrently, one subtask_id each. Merge instead of last-write-wins, which
    LangGraph would reject as a concurrent update to a non-reducer channel. A
    _ResetResults push (replan) replaces instead of merging."""
    if isinstance(b, _ResetResults):
        return dict(b)
    return {**a, **b}


def _append_failed(a: list[str], b: list[str]) -> list[str]:
    """Reducer for failed_subtasks: append by default (concurrent specialist failures),
    but a _ResetList push (replan) replaces — clears the previous attempt's failures."""
    if isinstance(b, _ResetList):
        return list(b)
    return a + list(b)


class IncidentStatus(StrEnum):
    OPEN = "open"
    PLANNING = "planning"
    DIAGNOSING = "diagnosing"
    AWAITING_APPROVAL = "awaiting_approval"  # Tier 3 — blocked on interrupt()
    ACTING = "acting"
    VERIFYING = "verifying"
    CLOSED = "closed"
    FAILED = "failed"


class AutonomyTier(IntEnum):
    AUTO = 1  # reversible, low impact — execute silently
    NOTIFY = 2  # execute + notify human
    APPROVE = 3  # block on interrupt() until human approves


# Reversibility + occupant impact set the action tier per domain. Only airquality
# has an actuator (ventilation: reversible, low-impact → Tier 1); the other domains
# have no autonomous action branch yet (Phase 5) and fall to the safest tier — they
# are resolved by a human at the Tier 3 interrupt. Lives here (not core/graph.py) so
# CriticAgent can read it without importing the graph module (circular import).
_TIER_BY_DOMAIN: dict[str, AutonomyTier] = {
    "airquality": AutonomyTier.AUTO,
}


def tier_for_sensor(sensor: str | None) -> AutonomyTier:
    """Action tier for the incident whose primary anomaly is on `sensor`. A domain
    with no actuator defaults to APPROVE (Tier 3 — human-only resolution)."""
    domain = SENSOR_DOMAIN.get(sensor or "", "airquality")
    return _TIER_BY_DOMAIN.get(domain, AutonomyTier.APPROVE)


# ── Replan budget (closed-loop completion — CLAUDE.md Principle #2) ────────────
# Attempts AFTER the first. A Tier 1/2 critic disapproval or a verifier "missed"
# routes a still-budgeted incident back through the planner (the replan node resets
# the attempt-scoped channels and bumps replan_count) instead of failing silently;
# once the budget is spent the incident terminates FAILED. Total planner runs per
# incident = MAX_REPLANS + 1.
MAX_REPLANS = 2


def replans_left(replan_count: int) -> bool:
    """True while the incident may still be retried. The critic and verifier read this
    to choose retry vs. terminal failure; the replan node then increments the count, so
    they both see the SAME (pre-increment) value and decide consistently with the router."""
    return replan_count < MAX_REPLANS


def reset_attempt_channels() -> dict[str, object]:
    """The state delta the replan node returns to clear one failed attempt: empty the
    two reducer channels (via the reset sentinels) and drop the stale action. The
    counter bump + status live with the node so this stays a pure data helper.
    critic_verdict / verifier_verdict are deliberately NOT cleared — the planner reads
    them as failure context, and the critic/verifier overwrite them next cycle."""
    return {
        "subtask_results": _ResetResults(),
        "failed_subtasks": _ResetList(),
        "action_taken": None,
    }


# ── Locked schemas (hard constraints — extra fields are forbidden) ────────────


class AnomalyRecord(BaseModel):
    """MonitorAgent's ONLY output shape (Hard Constraint #10). No diagnosis text:
    diagnosis is the Specialist's job; local Qwen3-8B fabricates causal narratives
    when asked to interpret anomalies (A4.5 Q16/Q17/Q22/Q23)."""

    model_config = ConfigDict(extra="forbid")

    anomaly: bool
    sensor: str
    value: float
    rule_violated: str


class ExpectedOutcome(BaseModel):
    """Typed outcome every Specialist must declare (Hard Constraint #13).

    Its existence is what makes the Verifier safe to run on local Qwen3-8B — a
    numeric comparison, not a judgement. Free-text ("should improve") forces the
    Verifier back onto cloud and breaks the 15-min latency budget.
    """

    model_config = ConfigDict(extra="forbid")

    target_metric: str  # e.g. "co2"
    target_value: float  # e.g. 800.0
    target_time_min: int  # minutes until the target should hold


# ── Planner output (minimal in Phase 0/1; full ReWOO DAG in Phase 2) ──────────


class Subtask(BaseModel):
    subtask_id: str  # e.g. "S1"
    domain: str  # airquality | thermal | lighting | acoustic
    goal: str  # may embed ReWOO refs like #S1.diagnosis, hydrated before it runs
    depends_on: list[str] = Field(default_factory=list)
    # Filled by the hydrate_placeholders node once depends_on results exist: goal
    # with every #{id}.{field} ref resolved. The specialist runs `hydrated_goal or
    # goal`. Kept separate from `goal` so the ReWOO template stays inspectable.
    hydrated_goal: str | None = None

    @property
    def effective_goal(self) -> str:
        return self.hydrated_goal or self.goal


class Plan(BaseModel):
    subtasks: list[Subtask] = Field(default_factory=list)


# ── Per-node result schemas ───────────────────────────────────────────────────


class SpecialistResult(BaseModel):
    """What a Specialist returns to the parent graph (its `final_diagnosis`)."""

    subtask_id: str
    diagnosis: str
    expected_outcome: ExpectedOutcome


class CriticVerdict(BaseModel):
    approved: bool
    unsupported_claims: list[str] = Field(default_factory=list)


class VerifierVerdict(BaseModel):
    verdict: str  # "met" | "missed"
    delta: float


# ── Parent graph state ────────────────────────────────────────────────────────


class MainIncidentState(BaseModel):
    """Shared state for MainIncidentGraph, persisted to Postgres."""

    # identity / lifecycle
    incident_id: str | None = None
    status: IncidentStatus = IncidentStatus.OPEN

    # monitor → incident
    anomaly: AnomalyRecord | None = None

    # memory_retrieve (inline Qdrant query from the planner node, not its own node)
    similar_cases: list[str] = Field(default_factory=list)  # episodic incident ids

    # planner
    current_plan: Plan | None = None
    replan_count: int = 0

    # specialists, keyed by subtask_id. Parallel fan-out (Send) writes this
    # concurrently → merge reducer (one subtask_id per branch, no key collisions).
    subtask_results: Annotated[dict[str, SpecialistResult], _merge_results] = Field(
        default_factory=dict
    )
    # subtask_ids whose specialist failed (no usable diagnosis). Append-reducer so
    # the dispatch loop counts them as "resolved" and never re-dispatches them —
    # a failed dependency simply leaves its dependents un-runnable and the wave
    # loop terminates instead of spinning. The replan node resets it (_ResetList)
    # so a retry's fresh plan is not blocked by the previous attempt's failures.
    failed_subtasks: Annotated[list[str], _append_failed] = Field(default_factory=list)

    # critic
    critic_verdict: CriticVerdict | None = None

    # autonomy gate → action
    autonomy_tier: AutonomyTier | None = None
    action_taken: str | None = None

    # verifier (runs 15 min after action)
    verifier_verdict: VerifierVerdict | None = None

    def primary_result(self) -> SpecialistResult | None:
        """The actionable subtask's result — the one whose domain matches the
        anomaly's sensor (SENSOR_DOMAIN). With a multi-subtask DAG the others are
        advisory (e.g. a thermal side-effect check), so autonomy_gate / action /
        verifier all key off this one. Falls back to the first available result."""
        if not self.subtask_results:
            return None
        if self.anomaly is not None and self.current_plan is not None:
            domain = SENSOR_DOMAIN.get(self.anomaly.sensor)
            for st in self.current_plan.subtasks:
                if st.domain == domain and st.subtask_id in self.subtask_results:
                    return self.subtask_results[st.subtask_id]
        return next(iter(self.subtask_results.values()))
