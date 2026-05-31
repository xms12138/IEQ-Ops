"""IEQ-Bench runner — load tasks → drive the REAL system entries → score → report.

Capability → system entry (all reused, never mocked):
  retrieval → mcp-rag-server retrieve              → metrics.score_retrieval
  generate  → SPECIALIST_SUBGRAPH ×N → CriticAgent → metrics.consistency_rate (+ hit)
  critic    → CriticAgent.run                       → metrics.score_critic
  planner   → PlannerAgent.run                      → metrics.score_plan

`generate` runs N times and feeds each diagnosis to the REAL critic; 1 − approval
rate is the generate-flaky number (≈33% measured by hand) that motivates the
Phase 4 generate/v4 fix. grade / rewrite / e2e are wired in a later milestone
(they need a builder single-node export or a checkpointer-driven scenario run).

  uv run python -m eval.runner --seed               # all seed tasks
  uv run python -m eval.runner --cap generate --n 10
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agents.critic import CriticAgent
from agents.planner import PlannerAgent
from agents.specialists.builder import SPECIALIST_SUBGRAPH
from core.config import get_settings
from core.logging import configure_logging, get_logger
from core.state import (
    AnomalyRecord,
    ExpectedOutcome,
    MainIncidentState,
    Plan,
    SpecialistResult,
    Subtask,
)
from eval import metrics
from eval.ieq_bench.loader import load_tasks
from eval.ieq_bench.schema import BenchTask, TaskResult
from mcp_servers.client import call_tool
from mcp_servers.rag.server import mcp as rag_server
from rag.retrieve import FINAL_TOP_K

log = get_logger("bench")
REPORTS = Path(__file__).parent / "reports"

# capability-specific handler return: (passed, score, detail, samples)
Outcome = tuple[bool, float, dict[str, Any], int]


class Runner:
    """Holds the shared agent instances (built once) and dispatches each task to
    the real system entry for its capability."""

    def __init__(self, n_samples: int = 10) -> None:
        self.n = n_samples
        self._planner: PlannerAgent | None = None
        self._critic: CriticAgent | None = None

    @property
    def planner(self) -> PlannerAgent:
        if self._planner is None:
            self._planner = PlannerAgent()
        return self._planner

    @property
    def critic(self) -> CriticAgent:
        if self._critic is None:
            self._critic = CriticAgent()
        return self._critic

    def run_task(self, task: BenchTask) -> TaskResult:
        handler = {
            "retrieval": self._run_retrieval,
            "generate": self._run_generate,
            "critic": self._run_critic,
            "planner": self._run_planner,
        }.get(task.capability)
        if handler is None:
            raise NotImplementedError(
                f"capability {task.capability!r} not wired in runner yet (task {task.task_id})"
            )
        passed, score, detail, samples = handler(task)
        return TaskResult(
            task_id=task.task_id,
            layer=task.layer,
            capability=task.capability,
            domain=task.domain,
            passed=passed,
            score=score,
            samples=samples,
            detail=detail,
        )

    def _run_retrieval(self, task: BenchTask) -> Outcome:
        q = task.input["query"]
        domain = task.input.get("domain", task.domain)
        k = int(task.expected.get("k", FINAL_TOP_K))
        chunks = call_tool(rag_server, "retrieve", query=q, domain=domain, top_k=k)
        sources = [c.source for c in chunks]
        passed, score, detail = metrics.score_retrieval(sources, task.expected)
        return passed, score, detail, 1

    def _run_generate(self, task: BenchTask) -> Outcome:
        """The generate-flaky probe: run the subgraph N times, feed every diagnosis
        to the real critic, report the approval (self-consistency) rate."""
        subtask = Subtask.model_validate(task.input["subtask"])
        anomaly = AnomalyRecord.model_validate(task.input["anomaly"])
        approvals: list[bool] = []
        hit_scores: list[float] = []
        n_none = 0
        for _ in range(self.n):
            out = SPECIALIST_SUBGRAPH.invoke({"subtask": subtask})
            diag = out["final_diagnosis"] if isinstance(out, dict) else out.final_diagnosis
            if diag is None:
                approvals.append(False)
                n_none += 1
                continue
            # incident_id=None: critic skips its ticket write on disapproval — a bench
            # probe has no Postgres incident row (otherwise update_incident raises).
            state = MainIncidentState(
                incident_id=None,
                anomaly=anomaly,
                current_plan=Plan(subtasks=[subtask]),
                subtask_results={subtask.subtask_id: diag},
            )
            verdict = self.critic.run(state)["critic_verdict"]
            approvals.append(bool(verdict.approved))
            if task.expected.get("gold_values"):
                _, hs, _ = metrics.score_generate_hit(diag.diagnosis, task.expected)
                hit_scores.append(hs)
        rate = metrics.consistency_rate(approvals)
        min_c = float(task.expected.get("min_consistency", 0.8))
        detail: dict[str, Any] = {
            "consistency_rate": rate,
            "disapproval_rate": round(1 - rate, 3),
            "approvals": approvals,
            "n_none": n_none,
            "min_consistency": min_c,
        }
        if hit_scores:
            detail["mean_hit"] = round(sum(hit_scores) / len(hit_scores), 3)
        return rate >= min_c, rate, detail, self.n

    def _run_critic(self, task: BenchTask) -> Outcome:
        anomaly = AnomalyRecord.model_validate(task.input["anomaly"])
        eo = ExpectedOutcome.model_validate(task.input["expected_outcome"])
        sid = task.input.get("subtask_id", "S1")
        result = SpecialistResult(
            subtask_id=sid, diagnosis=task.input["diagnosis"], expected_outcome=eo
        )
        subtask = Subtask(subtask_id=sid, domain=task.domain, goal="(bench)")
        state = MainIncidentState(
            incident_id=None,  # see _run_generate: critic must not write a ticket here
            anomaly=anomaly,
            current_plan=Plan(subtasks=[subtask]),
            subtask_results={sid: result},
        )
        verdict = self.critic.run(state)["critic_verdict"]
        passed, score, detail = metrics.score_critic(bool(verdict.approved), task.expected)
        detail["unsupported_claims"] = verdict.unsupported_claims
        return passed, score, detail, 1

    def _run_planner(self, task: BenchTask) -> Outcome:
        anomaly = AnomalyRecord.model_validate(task.input["anomaly"])
        state = MainIncidentState(incident_id=None, anomaly=anomaly)
        plan = self.planner.run(state)["current_plan"]
        passed, score, detail = metrics.score_plan(plan, anomaly.sensor, task.expected)
        return passed, score, detail, 1


def _print_table(summary: dict[str, Any]) -> None:
    print("\n" + "=" * 60)
    print(f"{'layer':<5} {'capability':<12} {'n':>3} {'pass':>6} {'score':>6}")
    print("-" * 60)
    for row in summary["by_capability"]:
        print(
            f"{row['layer']:<5} {row['capability']:<12} {row['n']:>3} "
            f"{row['pass_rate']:>6.2f} {row['mean_score']:>6.2f}"
        )
    print("-" * 60)
    o = summary["overall"]
    print(f"{'ALL':<5} {'':<12} {o['n']:>3} {o['pass_rate']:>6.2f} {o['mean_score']:>6.2f}")
    print("=" * 60)


def main() -> None:
    settings = get_settings()
    os.environ.setdefault("LANGFUSE_PUBLIC_KEY", settings.langfuse_public_key)
    os.environ.setdefault("LANGFUSE_SECRET_KEY", settings.langfuse_secret_key)
    os.environ.setdefault("LANGFUSE_HOST", settings.langfuse_host)
    configure_logging(settings.log_level)

    p = argparse.ArgumentParser(description="IEQ-Bench runner (Phase 4)")
    p.add_argument("--seed", action="store_true", help="run all seed tasks")
    p.add_argument("--cap", default=None, help="run only this capability")
    p.add_argument("--n", type=int, default=10, help="samples for stochastic caps (generate)")
    args = p.parse_args()

    tasks = load_tasks(capability=args.cap)
    if not tasks:
        print("no tasks found under eval/ieq_bench/tasks/*.jsonl")
        return
    runner = Runner(n_samples=args.n)
    results: list[TaskResult] = []
    for t in tasks:
        log.info("bench_task_start", task_id=t.task_id, cap=t.capability)
        try:
            r = runner.run_task(t)
        except NotImplementedError as exc:
            log.warning("bench_task_skip", task_id=t.task_id, reason=str(exc))
            continue
        results.append(r)
        mark = "✓" if r.passed else "✗"
        print(f"  {mark} {r.task_id:<30} score={r.score:.2f} samples={r.samples}")

    summary = metrics.aggregate(results)
    _print_table(summary)

    REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = REPORTS / f"seed-{stamp}.json"
    out.write_text(
        json.dumps(
            {"summary": summary, "results": [r.model_dump() for r in results]},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\nreport → {out}")


if __name__ == "__main__":
    main()
