"""IEQ-Bench runner — load tasks → drive the REAL system entries → score → report.

Capability → system entry (all reused, never mocked):
  retrieval → mcp-rag-server retrieve              → metrics.score_retrieval
  generate  → SPECIALIST_SUBGRAPH ×N → CriticAgent → metrics.consistency_rate (+ hit)
  critic    → CriticAgent.run                       → metrics.score_critic
  planner   → PlannerAgent.run                      → metrics.score_plan

`generate` runs N times and feeds each diagnosis to the REAL critic; 1 − approval
rate is the generate-flaky number (≈33% measured by hand) that motivates the
Phase 4 generate/v4 fix.

`--compare` is the L3 e2e contrast (the ≥10pp success criterion): the SAME anomaly
into both arms — system (planner + Agentic RAG) vs the naive ReAct baseline — judged
identically by the real CriticAgent (trust gate) + groundedness hit. Same base model
and tools on both, so the gap is attributable to architecture. grade / rewrite stay
for a later milestone (they need a builder single-node export).

  uv run python -m eval.runner --seed               # all seed capability tasks
  uv run python -m eval.runner --cap generate --n 10
  uv run python -m eval.runner --compare --n 5      # system vs baseline e2e table
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from agents.critic import CriticAgent
from agents.planner import PlannerAgent
from agents.specialists.builder import SPECIALIST_NODES, SPECIALIST_SUBGRAPH, SpecialistState
from core.config import get_settings
from core.logging import configure_logging, get_logger
from core.state import (
    SENSOR_DOMAIN,
    AnomalyRecord,
    ExpectedOutcome,
    MainIncidentState,
    Plan,
    SpecialistResult,
    Subtask,
)
from eval import metrics
from eval.baselines.react import ReActBaseline
from eval.ieq_bench.loader import load_tasks
from eval.ieq_bench.schema import AblationRow, BenchTask, ComparisonRow, TaskResult
from mcp_servers.client import call_tool
from mcp_servers.rag.server import mcp as rag_server
from memory.episodic import EpisodicCase
from rag.retrieve import FINAL_TOP_K
from sensing.simulator.scenarios import arm_value

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
        self._baseline: ReActBaseline | None = None

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

    @property
    def baseline(self) -> ReActBaseline:
        if self._baseline is None:
            self._baseline = ReActBaseline()
        return self._baseline

    def run_task(self, task: BenchTask) -> TaskResult:
        if task.capability in ("e2e", "recurrence"):
            raise NotImplementedError(
                f"{task.capability} runs via a dedicated mode (e2e → --compare, "
                f"recurrence → --ablate-memory), not the single-shot capability path "
                f"(task {task.task_id})"
            )
        handler = {
            "retrieval": self._run_retrieval,
            "generate": self._run_generate,
            "grade": self._run_grade,
            "rewrite": self._run_rewrite,
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

    def _run_grade(self, task: BenchTask) -> Outcome:
        """Isolate grade's self-reflective sufficiency judgement: feed it a CONTROLLED
        chunk set (from the task, not live retrieval) + the diagnostic goal, and check
        its sufficient verdict against gold. Fixed chunks strip retrieval noise, so a
        miss is grade's judgement — this is the probe that would catch a local-8B
        "confidently says enough" regression (Hard Constraint #11)."""
        subtask = Subtask(subtask_id="S1", domain=task.domain, goal=task.input["goal"])
        chunks = [dict(c) for c in task.input.get("chunks", [])]
        state = SpecialistState(subtask=subtask, retrieved_chunks=chunks)
        out = SPECIALIST_NODES["grade"](state)
        passed, score, detail = metrics.score_grade(bool(out["sufficient"]), task.expected)
        detail["grade_reason"] = out.get("grade_reason", "")
        return passed, score, detail, 1

    def _run_rewrite(self, task: BenchTask) -> Outcome:
        """rewrite is a short-string transform (LOCAL tier): turn a weak query that
        ranks the gold chunk poorly into one that ranks it well. On the placeholder
        corpus top_k(=5) ≥ every domain's pool, so mere recall is trivially 1.0 — the
        discriminating signal is the gold chunk's RANK (MRR), which the reranker still
        varies by query. Run N times (rewrite is temp>0), report mean gold-MRR after
        rewrite vs the weak query's MRR before; pass if after ≥ min_mrr."""
        domain = task.domain
        goal = task.input.get("goal", task.input["query"])
        subtask = Subtask(subtask_id="S1", domain=domain, goal=goal)
        k = int(task.expected.get("k", FINAL_TOP_K))

        def gold_mrr(query: str) -> float:
            chunks = call_tool(rag_server, "retrieve", query=query, domain=domain, top_k=k)
            _, rr, _ = metrics.score_retrieval([c.source for c in chunks], task.expected)
            return rr

        mrr_before = gold_mrr(task.input["query"])
        after: list[float] = []
        for _ in range(self.n):
            state = SpecialistState(
                subtask=subtask,
                current_query=task.input["query"],
                grade_reason=task.input.get("grade_reason", ""),
                rewrite_count=0,
            )
            new_q = SPECIALIST_NODES["rewrite"](state)["current_query"]
            after.append(gold_mrr(new_q))
        mrr_after = round(sum(after) / len(after), 3) if after else 0.0
        min_mrr = float(task.expected.get("min_mrr", 0.5))
        detail = {
            "mrr_before": round(mrr_before, 3),
            "mrr_after": mrr_after,
            "improved": mrr_after >= mrr_before,
            "min_mrr": min_mrr,
            "n": self.n,
        }
        return mrr_after >= min_mrr, mrr_after, detail, self.n

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

    # ── L3 e2e: dual-arm comparison (system vs baseline, identical judges) ────────

    def _system_diagnose(self, anomaly: AnomalyRecord) -> SpecialistResult | None:
        """System arm: planner (Plan-and-Execute DAG + episodic recall) → the primary
        subtask (the one routing to the anomaly's domain) → SpecialistSubgraph (Agentic
        RAG). Starts from the same anomaly the baseline gets; this whole path is the
        architecture being credited against the naive loop."""
        state = MainIncidentState(incident_id=None, anomaly=anomaly)
        plan = self.planner.run(state)["current_plan"]
        domain = SENSOR_DOMAIN.get(anomaly.sensor)
        primary = next((s for s in plan.subtasks if s.domain == domain), plan.subtasks[0])
        out = SPECIALIST_SUBGRAPH.invoke({"subtask": primary})
        return out["final_diagnosis"] if isinstance(out, dict) else out.final_diagnosis

    def _baseline_diagnose(self, anomaly: AnomalyRecord) -> SpecialistResult | None:
        """Baseline arm: naive ReAct loop on the same anomaly. Its `finish` already
        emits the typed {diagnosis, expected_outcome}, so we wrap it into the same
        SpecialistResult shape and judge both arms identically. A run that never
        finishes, or returns a malformed outcome, is a baseline failure → None."""
        res = self.baseline.run(anomaly.model_dump())
        final = res.get("final")
        if not final:
            return None
        try:
            eo = ExpectedOutcome.model_validate(final["expected_outcome"])
            return SpecialistResult(
                subtask_id="S1", diagnosis=str(final["diagnosis"]), expected_outcome=eo
            )
        except (ValidationError, KeyError, TypeError):
            return None

    def _judge(
        self, diag: SpecialistResult | None, anomaly: AnomalyRecord, expected: dict[str, Any]
    ) -> tuple[bool, float | None]:
        """The shared, arm-blind judge: (1) the REAL CriticAgent's approve/reject — the
        system's own trust gate, i.e. "would this diagnosis be allowed to act?" — and
        (2) the groundedness hit proxy when the task declares gold_values. Returns
        (critic_approved, hit_or_None). A None diagnosis fails the gate."""
        if diag is None:
            return False, (0.0 if expected.get("gold_values") else None)
        domain = SENSOR_DOMAIN.get(anomaly.sensor, anomaly.sensor)
        subtask = Subtask(subtask_id=diag.subtask_id, domain=domain, goal="(bench)")
        state = MainIncidentState(
            incident_id=None,  # bench probe: critic must not write a ticket (see _run_critic)
            anomaly=anomaly,
            current_plan=Plan(subtasks=[subtask]),
            subtask_results={diag.subtask_id: diag},
        )
        approved = bool(self.critic.run(state)["critic_verdict"].approved)
        hit: float | None = None
        if expected.get("gold_values"):
            _, hit, _ = metrics.score_generate_hit(diag.diagnosis, expected)
        return approved, hit

    def compare(self, tasks: list[BenchTask], n: int) -> list[ComparisonRow]:
        """For each e2e task, run BOTH arms N times on the same anomaly and score them
        with the same judge. Before each task the simulator room is armed to the anomaly's
        exact value so the baseline's read_sensors agrees with its own prompt (the system
        arm takes the anomaly directly, so without this only the baseline would face a
        contradicting in-band reading — an unfair handicap, not an architecture gap).
        arm_value handles ANY task value, so high-value discriminating tasks (e.g. the
        self-contradiction traps) stay fair without a hand-built named scenario each."""
        rows: list[ComparisonRow] = []
        for task in tasks:
            anomaly = AnomalyRecord.model_validate(task.input["anomaly"])
            arm_value(anomaly.sensor, anomaly.value)
            sys_ok: list[bool] = []
            base_ok: list[bool] = []
            sys_hits: list[float] = []
            base_hits: list[float] = []
            base_no_finish = 0
            for _ in range(n):
                s_appr, s_hit = self._judge(self._system_diagnose(anomaly), anomaly, task.expected)
                sys_ok.append(s_appr)
                if s_hit is not None:
                    sys_hits.append(s_hit)
                bdiag = self._baseline_diagnose(anomaly)
                if bdiag is None:
                    base_no_finish += 1
                b_appr, b_hit = self._judge(bdiag, anomaly, task.expected)
                base_ok.append(b_appr)
                if b_hit is not None:
                    base_hits.append(b_hit)
            ssr = round(sum(sys_ok) / len(sys_ok), 3)
            bsr = round(sum(base_ok) / len(base_ok), 3)
            row = ComparisonRow(
                task_id=task.task_id,
                domain=task.domain,
                n=n,
                system_success=ssr,
                baseline_success=bsr,
                gap_pp=round((ssr - bsr) * 100, 1),
                system_hit=round(sum(sys_hits) / len(sys_hits), 3) if sys_hits else None,
                baseline_hit=round(sum(base_hits) / len(base_hits), 3) if base_hits else None,
                baseline_no_finish=base_no_finish,
            )
            rows.append(row)
            extra = f" base_no_finish={base_no_finish}" if base_no_finish else ""
            print(
                f"  {row.task_id:<18} sys={ssr:.2f} base={bsr:.2f} gap={row.gap_pp:+.1f}pp{extra}"
            )
        return rows

    # ── memory ablation: same planner, recall ON vs OFF (Week 8 vs Week 1, offline) ──

    @staticmethod
    def _plan_text(plan: Plan) -> str:
        """All subtask goals joined + lowercased — where a recalled building-specific
        cause/fix would surface if memory informed the plan."""
        return " ".join(s.goal for s in plan.subtasks).lower()

    def ablate_memory(self, tasks: list[BenchTask]) -> list[AblationRow]:
        """For each recurrence task, run the SAME planner on the SAME anomaly twice: once
        with an empty recall (memory OFF) and once with the task's seeded past case (memory
        ON). The case carries building-specific knowledge (a cause/fix NOT in the standards
        corpus); the metric is whether that knowledge surfaces in the plan's subtask goals.
        lift = recall_on − recall_off is the isolated memory contribution. Planner is
        temperature 0, so each side is deterministic — no sampling needed."""
        rows: list[AblationRow] = []
        for task in tasks:
            anomaly = AnomalyRecord.model_validate(task.input["anomaly"])
            case = EpisodicCase.model_validate(task.input["episode"])
            state = MainIncidentState(incident_id=None, anomaly=anomaly)
            plan_off = self.planner.plan_with_recall(state, [])
            plan_on = self.planner.plan_with_recall(state, [case])
            gold = [g.lower() for g in task.expected.get("recall_gold", [])]
            text_off, text_on = self._plan_text(plan_off), self._plan_text(plan_on)
            hit_off = any(g in text_off for g in gold)
            hit_on = any(g in text_on for g in gold)
            row = AblationRow(
                task_id=task.task_id,
                domain=task.domain,
                recall_off=hit_off,
                recall_on=hit_on,
                lift=int(hit_on) - int(hit_off),
                shape_off=[s.subtask_id for s in plan_off.subtasks],
                shape_on=[s.subtask_id for s in plan_on.subtasks],
                detail={
                    "gold": gold,
                    "verdict": case.verdict,
                    "goals_off": [s.goal for s in plan_off.subtasks],
                    "goals_on": [s.goal for s in plan_on.subtasks],
                },
            )
            rows.append(row)
            print(
                f"  {row.task_id:<22} off={'Y' if hit_off else 'n'} "
                f"on={'Y' if hit_on else 'n'} lift={row.lift:+d}"
            )
        return rows


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


def _print_compare_table(rows: list[ComparisonRow]) -> float:
    """Side-by-side system vs baseline success (critic-approval rate) + the gap.
    Returns the macro-mean gap (pp) the ≥10pp success criterion is checked against."""
    print("\n" + "=" * 74)
    print(f"{'task':<18} {'domain':<11} {'n':>3} {'system':>7} {'baseline':>9} {'gap':>9}")
    print("-" * 74)
    for r in rows:
        print(
            f"{r.task_id:<18} {r.domain:<11} {r.n:>3} {r.system_success:>7.2f} "
            f"{r.baseline_success:>9.2f} {r.gap_pp:>+7.1f}pp"
        )
    print("-" * 74)
    sys_mean = round(sum(r.system_success for r in rows) / len(rows), 3)
    base_mean = round(sum(r.baseline_success for r in rows) / len(rows), 3)
    gap = round((sys_mean - base_mean) * 100, 1)
    print(f"{'MEAN':<18} {'':<11} {'':>3} {sys_mean:>7.2f} {base_mean:>9.2f} {gap:>+7.1f}pp")
    print("=" * 74)
    ok = "✓ meets ≥10pp" if gap >= 10 else "✗ <10pp — needs more discriminating / 200-task set"
    print(f"success criterion (system − baseline ≥ 10pp): {ok}")
    return gap


def _print_ablation_table(rows: list[AblationRow]) -> float:
    """Memory OFF vs ON: did the building-specific recalled knowledge surface in the plan?
    Returns the macro recall-lift (fraction of tasks where memory added knowledge the
    no-memory planner missed) — the offline Week 8 vs Week 1 signal."""
    print("\n" + "=" * 64)
    print(f"{'task':<24} {'domain':<11} {'mem off':>8} {'mem on':>7} {'lift':>6}")
    print("-" * 64)
    for r in rows:
        print(
            f"{r.task_id:<24} {r.domain:<11} {'hit' if r.recall_off else '—':>8} "
            f"{'hit' if r.recall_on else '—':>7} {r.lift:>+6d}"
        )
    print("-" * 64)
    lift = round(sum(r.lift for r in rows) / len(rows), 3) if rows else 0.0
    on_rate = round(sum(r.recall_on for r in rows) / len(rows), 3) if rows else 0.0
    off_rate = round(sum(r.recall_off for r in rows) / len(rows), 3) if rows else 0.0
    print(f"{'MACRO':<24} {'':<11} {off_rate:>8.2f} {on_rate:>7.2f} {lift:>+6.2f}")
    print("=" * 64)
    print(f"memory recall-lift (on − off, building-specific knowledge in plan): {lift:+.2f}")
    return lift


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
    p.add_argument(
        "--compare",
        action="store_true",
        help="L3 e2e: run system vs ReAct baseline on the same anomalies and report the gap",
    )
    p.add_argument(
        "--ablate-memory",
        action="store_true",
        help="L3 recurrence: same planner, recall ON vs OFF, report the memory lift",
    )
    p.add_argument(
        "--only",
        default=None,
        help="filter tasks to those whose task_id contains this substring (compare/ablate)",
    )
    args = p.parse_args()

    if args.ablate_memory:
        rec = load_tasks(capability="recurrence")
        if args.only:
            rec = [t for t in rec if args.only in t.task_id]
        if not rec:
            print("no recurrence tasks found under eval/ieq_bench/tasks/*.jsonl")
            return
        print(f"\nIEQ-Bench memory ablation — planner recall OFF vs ON ({len(rec)} tasks)")
        runner = Runner()
        rows = runner.ablate_memory(rec)
        lift = _print_ablation_table(rows)
        REPORTS.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        out = REPORTS / f"ablate-memory-{stamp}.json"
        out.write_text(
            json.dumps(
                {"macro_lift": lift, "rows": [r.model_dump() for r in rows]},
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        print(f"\nreport → {out}")
        return

    if args.compare:
        e2e = load_tasks(capability="e2e")
        if args.only:
            e2e = [t for t in e2e if args.only in t.task_id]
        if not e2e:
            print("no e2e tasks found under eval/ieq_bench/tasks/*.jsonl")
            return
        print(f"\nIEQ-Bench e2e — system vs ReAct baseline (n={args.n}/task, same model + tools)")
        runner = Runner(n_samples=args.n)
        rows = runner.compare(e2e, args.n)
        gap = _print_compare_table(rows)
        REPORTS.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        out = REPORTS / f"compare-{stamp}.json"
        out.write_text(
            json.dumps(
                {"n_per_task": args.n, "macro_gap_pp": gap, "rows": [r.model_dump() for r in rows]},
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        print(f"\nreport → {out}")
        return

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
