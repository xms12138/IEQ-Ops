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

from pydantic import BaseModel, ConfigDict, Field


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

    # specialists, keyed by subtask_id (hydrates ReWOO placeholders downstream).
    # NOTE Phase 2: parallel specialist fan-out writes this key concurrently and
    # will need an Annotated reducer to merge instead of overwrite.
    subtask_results: dict[str, SpecialistResult] = Field(default_factory=dict)

    # critic
    critic_verdict: CriticVerdict | None = None

    # autonomy gate → action
    autonomy_tier: AutonomyTier | None = None
    action_taken: str | None = None

    # verifier (runs 15 min after action)
    verifier_verdict: VerifierVerdict | None = None
