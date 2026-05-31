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
Capability = Literal["retrieval", "grade", "rewrite", "generate", "critic", "planner", "e2e"]
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
