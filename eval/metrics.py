"""Deterministic scorers — no LLM, gold comparison.

Each `score_*` takes (system output already extracted to plain types, task
`expected`) and returns a `Score` = (passed, score, detail). The runner pairs each
capability with one scorer; LLM-judged dimensions (groundedness / plan quality /
e2e answer text) go through eval/judge.py instead.

`generate` self-consistency is NOT a single-shot scorer: the runner runs generate
N times, feeds each diagnosis to the real CriticAgent, and `consistency_rate`
folds the approvals into 1 − (critic disapproval rate) — the generate-flaky number
that motivates the Phase 4 generate/v4 fix.

`aggregate` rolls per-(layer, capability) pass-rate + mean score for the report.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from core.state import SENSOR_DOMAIN, Plan, Subtask
from eval.ieq_bench.schema import TaskResult

Score = tuple[bool, float, dict[str, Any]]


# ── L1 retrieval ──────────────────────────────────────────────────────────────


def score_retrieval(retrieved_sources: list[str], expected: dict[str, Any]) -> Score:
    """hit@k + MRR against gold standard sources. `expected`:
    {gold_sources: [...], k?: int}. Match is by source id (e.g. "ashrae-62.1")."""
    gold = set(expected.get("gold_sources", []))
    k = int(expected.get("k", len(retrieved_sources)))
    topk = retrieved_sources[:k]
    hit = any(s in gold for s in topk)
    rr = 0.0
    for rank, s in enumerate(topk, 1):
        if s in gold:
            rr = 1.0 / rank
            break
    return (
        hit,
        round(rr, 3),
        {"hit@k": hit, "mrr": round(rr, 3), "k": k, "top": topk, "gold": sorted(gold)},
    )


# ── L2 grade / rewrite / generate / critic / planner ──────────────────────────


def score_grade(sufficient: bool, expected: dict[str, Any]) -> Score:
    """grade completeness vs gold. `expected`: {sufficient: bool}."""
    gold = bool(expected.get("sufficient"))
    passed = sufficient == gold
    return passed, 1.0 if passed else 0.0, {"got": sufficient, "gold": gold}


def score_rewrite(recalled_gold: bool, expected: dict[str, Any]) -> Score:
    """Did the rewritten query's retrieval surface the previously-missing gold
    chunk? The runner computes the bool (re-retrieve, check gold source present)."""
    passed = bool(recalled_gold)
    return passed, 1.0 if passed else 0.0, {"recalled_gold": passed}


def score_generate_hit(diagnosis: str, expected: dict[str, Any]) -> Score:
    """A4.5 hit-only proxy: does the grounded diagnosis SURFACE the specific values
    / citations present in the standards (the 14pp gap local 8B fails on)?
    `expected`: {gold_values: ["1000 ppm", "ASHRAE 62.1", ...]}. Case-insensitive
    substring. Empty gold → skip (returns pass, so it never penalises a task that
    only checks self-consistency)."""
    gold = [str(g) for g in expected.get("gold_values", [])]
    if not gold:
        return True, 1.0, {"note": "no gold_values — hit check skipped"}
    low = diagnosis.lower()
    hits = [g for g in gold if g.lower() in low]
    score = len(hits) / len(gold)
    return (
        len(hits) == len(gold),
        round(score, 3),
        {"hit": hits, "missed": [g for g in gold if g not in hits]},
    )


def score_critic(approved: bool, expected: dict[str, Any]) -> Score:
    """critic verdict vs gold. `expected`: {approved: bool}. A bad diagnosis the
    critic SHOULD reject has expected.approved = False."""
    gold = bool(expected.get("approved"))
    passed = approved == gold
    return passed, 1.0 if passed else 0.0, {"got": approved, "gold": gold}


def score_verifier(verdict: str, expected: dict[str, Any]) -> Score:
    """verifier numeric verdict vs gold. `expected`: {verdict: "met"|"missed"}."""
    gold = str(expected.get("verdict", ""))
    passed = verdict == gold
    return passed, 1.0 if passed else 0.0, {"got": verdict, "gold": gold}


def _has_cycle(subtasks: list[Subtask]) -> bool:
    graph = {s.subtask_id: list(s.depends_on) for s in subtasks}
    state: dict[str, int] = {}  # 0/absent=unvisited, 1=on-stack, 2=done

    def dfs(node: str) -> bool:
        if state.get(node) == 1:
            return True
        if state.get(node) == 2:
            return False
        state[node] = 1
        for nxt in graph.get(node, []):
            if nxt in graph and dfs(nxt):
                return True
        state[node] = 2
        return False

    return any(dfs(n) for n in graph)


def score_plan(plan: Plan, sensor: str, expected: dict[str, Any]) -> Score:
    """ReWOO DAG structural validity (deterministic — plan *quality* is the LLM
    judge's job). Checks: unique subtask_ids, deps reference real ids, acyclic,
    a subtask routes to the anomaly's primary domain (SENSOR_DOMAIN). `expected`
    may add {max_subtasks: int, require_domains: [...]}."""
    ids = [s.subtask_id for s in plan.subtasks]
    issues: list[str] = []
    if len(ids) != len(set(ids)):
        issues.append("duplicate subtask_id")
    idset = set(ids)
    for s in plan.subtasks:
        for dep in s.depends_on:
            if dep not in idset:
                issues.append(f"{s.subtask_id} depends on unknown {dep}")
    if _has_cycle(plan.subtasks):
        issues.append("dependency cycle")
    domains = {s.domain for s in plan.subtasks}
    want = SENSOR_DOMAIN.get(sensor)
    if want and want not in domains:
        issues.append(f"no subtask routes to primary domain {want!r}")
    for req in expected.get("require_domains", []):
        if req not in domains:
            issues.append(f"missing required domain {req!r}")
    max_st = expected.get("max_subtasks")
    if max_st is not None and len(plan.subtasks) > int(max_st):
        issues.append(f"{len(plan.subtasks)} subtasks > max {max_st}")
    passed = not issues
    return (
        passed,
        1.0 if passed else 0.0,
        {"subtasks": ids, "domains": sorted(domains), "issues": issues},
    )


# ── generate self-consistency (multi-sample) ──────────────────────────────────


def consistency_rate(approvals: list[bool]) -> float:
    """generate self-consistency = fraction of N samples the critic approved.
    1 − this = the critic disapproval (flaky) rate."""
    return round(sum(approvals) / len(approvals), 3) if approvals else 0.0


# ── aggregation ───────────────────────────────────────────────────────────────


def aggregate(results: list[TaskResult]) -> dict[str, Any]:
    """Per-(layer, capability) pass-rate + mean score, plus an overall line."""
    buckets: dict[tuple[str, str], list[TaskResult]] = defaultdict(list)
    for r in results:
        buckets[(r.layer, r.capability)].append(r)
    rows: list[dict[str, Any]] = []
    for (layer, cap), rs in sorted(buckets.items()):
        n = len(rs)
        rows.append(
            {
                "layer": layer,
                "capability": cap,
                "n": n,
                "pass_rate": round(sum(r.passed for r in rs) / n, 3),
                "mean_score": round(sum(r.score for r in rs) / n, 3),
            }
        )
    n_all = len(results)
    overall = {
        "n": n_all,
        "pass_rate": round(sum(r.passed for r in results) / n_all, 3) if n_all else 0.0,
        "mean_score": round(sum(r.score for r in results) / n_all, 3) if n_all else 0.0,
    }
    return {"by_capability": rows, "overall": overall}
