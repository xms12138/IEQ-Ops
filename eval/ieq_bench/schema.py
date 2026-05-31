"""IEQ-Bench task schema — one typed record per benchmark task.

A BenchTask is *capability-addressed*: `capability` selects which system entry the
runner drives (retrieval / grade / rewrite / generate / critic / planner / e2e),
and `input`/`expected` are capability-specific payloads the runner + metrics
interpret. They stay `dict` (not a discriminated union) because the seven
capability shapes are heterogeneous and bench code is outside `mypy --strict`
(CLAUDE.md scopes strict to core/); the runner validates shape per capability at
dispatch time.

Layers mirror the node tiers in ops/llm_routing.md:
  L1  retrieval / knowledge — the deterministic RAG primitive
  L2  per-node capability   — grade / rewrite / generate / critic / planner
  L3  end-to-end incident   — the full MainIncidentGraph closed loop

`judge_type` picks the scorer: "deterministic" → eval/metrics.py (no LLM, gold
comparison); "llm" → eval/judge.py (groundedness / plan-quality / e2e answer).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Layer = Literal["L1", "L2", "L3"]
Capability = Literal[
    "retrieval", "grade", "rewrite", "generate", "critic", "planner", "e2e", "recurrence"
]
JudgeType = Literal["deterministic", "llm"]


class BenchTask(BaseModel):
    """One IEQ-Bench task. `input`/`expected` are capability-specific (see runner)."""

    model_config = ConfigDict(extra="forbid")

    task_id: str  # e.g. "L2-generate-co2-001"
    layer: Layer
    capability: Capability
    domain: str  # airquality | thermal | lighting | acoustic | mixed
    input: dict[str, Any]
    expected: dict[str, Any] = Field(default_factory=dict)
    judge_type: JudgeType = "deterministic"
    notes: str = ""


class TaskResult(BaseModel):
    """One task's scored outcome — what the runner collects and aggregates over.

    `score` is 0..1 unless the metric is rank-based (hit@k / MRR also land in 0..1).
    `samples` > 1 for stochastic capabilities (generate flaky runs N times and
    reports the pass fraction)."""

    task_id: str
    layer: Layer
    capability: Capability
    domain: str
    passed: bool
    score: float
    samples: int = 1
    detail: dict[str, Any] = Field(default_factory=dict)  # metric internals / judge reason


class ComparisonRow(BaseModel):
    """One L3 e2e task scored on BOTH arms — IEQ-Ops (planner + Agentic RAG) vs the
    naive ReAct baseline — under identical judges (the real CriticAgent's trust gate
    + groundedness hit). `*_success` is the critic-approval rate over N stochastic
    samples; `gap_pp` is the headline (system − baseline) in percentage points that
    the ≥10pp success criterion is measured against. Same base model + same tools on
    both arms, so the gap is attributable to architecture, not the model."""

    task_id: str
    domain: str
    n: int
    system_success: float
    baseline_success: float
    gap_pp: float
    system_hit: float | None = None  # mean groundedness hit; None when no gold_values
    baseline_hit: float | None = None
    baseline_no_finish: int = 0  # baseline samples that never produced a finish
    detail: dict[str, Any] = Field(default_factory=dict)


class AblationRow(BaseModel):
    """One memory-ablation task: the SAME planner on the SAME anomaly, run with the
    recalled past case (memory ON) vs an empty recall (memory OFF). `recall_on`/`recall_off`
    is whether the building-specific knowledge that ONLY memory carries (a cause/fix NOT in
    the standards corpus) surfaced in the plan's subtask goals; `lift` = on − off is the
    memory contribution this task isolates — the OFFLINE analogue of the dissertation's
    Week 8 vs Week 1 claim. Planner runs at temperature 0, so each side is deterministic
    (no sampling). This is an ablation, not a system-vs-ReAct contrast: ReAct has neither a
    planner nor memory, so it cannot isolate the memory channel."""

    task_id: str
    domain: str
    recall_off: bool
    recall_on: bool
    lift: int  # int(recall_on) − int(recall_off); +1 = memory added the knowledge
    shape_off: list[str]  # subtask ids without recall
    shape_on: list[str]  # subtask ids with recall
    detail: dict[str, Any] = Field(default_factory=dict)
