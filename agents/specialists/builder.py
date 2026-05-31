"""SpecialistSubgraph factory — the 5-node Agentic RAG loop, compiled ONCE.

    decompose → retrieve → grade ⇄ rewrite → generate

All four specialist domains share this single compiled instance; the domain comes
in at runtime via `subtask.domain` (selects the mcp-rag-server corpus slice), so
this is NOT recompiled per incident (CLAUDE.md). The four agents/specialists/
{domain}.py files are thin wrappers that invoke SPECIALIST_SUBGRAPH and lift only
`final_diagnosis` back into the parent graph.

This is the IEQ-Ops rebuild of douluo/agentic_rag.py. What changed:
  - LLM calls go through core/router.py per-node (decompose/grade/generate → FAST
    cloud flash, rewrite → LOCAL). grade & generate are mandatory cloud — never
    local (Hard Constraint #11). douluo hard-coded one model.
  - retrieve calls mcp-rag-server (no LLM here — Hard Constraint #9).
  - generate output is Pydantic-locked to SpecialistResult{diagnosis,
    expected_outcome} (Hard Constraint #13); douluo emitted free text.

State isolation (🔴 Phase 2 risk #2): SpecialistState is the subgraph's OWN schema.
Its bulky fields (retrieved_chunks, grade_reason, rewrite_count) never enter the
parent's checkpoint — the wrapper passes only `subtask` in and reads only
`final_diagnosis` out. This is what keeps MainIncidentGraph's checkpoint small.
"""

from __future__ import annotations

import json
import operator
import re
from typing import Annotated, Any

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field, ValidationError

from agents.prompt_loader import load_prompt
from core.logging import get_logger
from core.router import Router, RouterExhausted
from core.state import (
    ExpectedOutcome,
    SpecialistResult,
    Subtask,
)
from mcp_servers.client import call_tool
from mcp_servers.rag.server import mcp as rag_server
from rag.retrieve import FINAL_TOP_K

log = get_logger("specialist")

MAX_REWRITES = 3  # rewrite cap per subtask (CLAUDE.md: "Retries are capped at 3")
_JSON = {"type": "json_object"}
# v4 reasoning models otherwise spend the token budget on reasoning_content and
# sometimes return an empty message.content. These nodes are structured (JSON /
# short-string), not reasoning-depth tasks, so disable thinking — also cuts latency
# sharply. douluo did the same. (Planner stays on thinking: DAG needs reasoning.)
_NO_THINK: dict[str, Any] = {"thinking": {"type": "disabled"}}


class SpecialistState(BaseModel):
    """Isolated subgraph state — lives here, NOT in core/state.py, so it cannot
    leak into the parent checkpoint."""

    # ── in (from parent) ──
    subtask: Subtask
    # ── decompose ──
    sub_queries: list[str] = Field(default_factory=list)
    # ── rewrite-loop control ──
    current_query: str = ""
    rewrite_count: int = 0
    # ── retrieve (accumulated across rounds; reducer appends, node dedups) ──
    retrieved_chunks: Annotated[list[dict[str, Any]], operator.add] = Field(default_factory=list)
    # ── grade ──
    sufficient: bool = False
    grade_reason: str = ""
    # ── out (to parent) — the ONLY field the wrapper reads back ──
    final_diagnosis: SpecialistResult | None = None


def _extract_json(text: str) -> dict[str, Any]:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError(f"no JSON in response: {text[:120]!r}")
    data: Any = json.loads(m.group(0))
    if not isinstance(data, dict):
        raise ValueError(f"expected a JSON object, got {type(data).__name__}")
    return data


def _clean_query(text: str) -> str:
    text = re.sub(r"^(new query|rewritten query)\s*[:：]\s*", "", text.strip(), flags=re.I)
    return text.strip("\"'`").strip()


# ── node factories (each closes over the shared Router) ───────────────────────


def _make_decompose(router: Router) -> Any:
    tmpl = load_prompt("specialist/decompose")

    def decompose(state: SpecialistState) -> dict[str, Any]:
        st = state.subtask
        prompt = tmpl.safe_substitute(domain=st.domain, goal=st.goal)
        subs: list[str]
        try:
            data = _extract_json(
                router.complete(
                    "specialist.decompose",
                    [{"role": "user", "content": prompt}],
                    response_format=_JSON,
                    extra_body=_NO_THINK,
                    temperature=0.0,
                )
            )
            subs = data.get("sub_queries") or [st.goal]
            if not isinstance(subs, list) or not all(
                isinstance(s, str) and s.strip() for s in subs
            ):
                subs = [st.goal]
        except (RouterExhausted, ValueError, json.JSONDecodeError) as exc:
            log.warning("decompose_fallback", error=str(exc))  # degrade to single-query
            subs = [st.goal]
        subs = subs[:3]  # hard cap ≤3 (ops/llm_routing.md #4a)
        log.info("decompose", subtask_id=st.subtask_id, n_sub=len(subs))
        return {"sub_queries": subs, "current_query": st.goal, "rewrite_count": 0}

    return decompose


def _make_retrieve() -> Any:
    def retrieve(state: SpecialistState) -> dict[str, Any]:
        # round 0 fans over all sub-queries; rewrite rounds re-query the rewritten one
        queries = state.sub_queries if state.rewrite_count == 0 else [state.current_query]
        seen = {(c["source"], c["chunk_idx"]) for c in state.retrieved_chunks}
        new: list[dict[str, Any]] = []
        for q in queries:
            for c in call_tool(
                rag_server, "retrieve", query=q, domain=state.subtask.domain, top_k=FINAL_TOP_K
            ):
                # MCP structured output → attribute access (FastMCP RootModel)
                key = (c.source, c.chunk_idx)
                if key in seen:
                    continue
                seen.add(key)
                new.append(
                    {
                        "text": c.text,
                        "source": c.source,
                        "domain": c.domain,
                        "chunk_idx": c.chunk_idx,
                        "score": c.score,
                    }
                )
        log.info("retrieve", round=state.rewrite_count, new=len(new), total=len(seen))
        return {"retrieved_chunks": new}  # Annotated[..., add] appends to the accumulator

    return retrieve


def _make_grade(router: Router) -> Any:
    tmpl = load_prompt("specialist/grade")

    def grade(state: SpecialistState) -> dict[str, Any]:
        chunks = state.retrieved_chunks
        context = (
            "\n\n---\n\n".join(f"[{i + 1}] {c['text']}" for i, c in enumerate(chunks))
            if chunks
            else "(none)"
        )
        prompt = tmpl.safe_substitute(goal=state.subtask.goal, context=context)
        try:
            data = _extract_json(
                router.complete(
                    "specialist.grade",
                    [{"role": "user", "content": prompt}],
                    response_format=_JSON,
                    extra_body=_NO_THINK,
                    temperature=0.0,
                )
            )
            sufficient = bool(data.get("sufficient", False))
            reason = str(data.get("reason", "") or "")
        except (RouterExhausted, ValueError, json.JSONDecodeError) as exc:
            # Conservative fallback (ops/llm_routing.md #4c): force one rewrite rather
            # than a false-positive "good enough".
            log.warning("grade_fallback", error=str(exc))
            sufficient, reason = False, "(grade unavailable — forcing one rewrite)"
        log.info("grade", sufficient=sufficient, n_chunks=len(chunks))
        return {"sufficient": sufficient, "grade_reason": reason}

    return grade


def _make_rewrite(router: Router) -> Any:
    tmpl = load_prompt("specialist/rewrite")

    def rewrite(state: SpecialistState) -> dict[str, Any]:
        old = state.current_query or state.subtask.goal
        prompt = tmpl.safe_substitute(query=old, reason=state.grade_reason or "(none)")
        try:  # plain string out (no JSON) — short-string transform, LOCAL tier (#4d)
            new_q = (
                _clean_query(
                    router.complete(
                        "specialist.rewrite",
                        [{"role": "user", "content": prompt}],
                        extra_body=_NO_THINK,
                        temperature=0.3,
                    )
                )
                or old
            )
        except RouterExhausted as exc:
            log.warning("rewrite_fallback", error=str(exc))
            new_q = old
        log.info("rewrite", count=state.rewrite_count + 1, old=old[:40], new=new_q[:40])
        return {"current_query": new_q, "rewrite_count": state.rewrite_count + 1}

    return rewrite


def _make_generate(router: Router) -> Any:
    tmpl = load_prompt("specialist/generate", 4)

    def generate(state: SpecialistState) -> dict[str, Any]:
        st = state.subtask
        chunks = state.retrieved_chunks
        context = (
            "\n\n---\n\n".join(
                f"[{i + 1} · {c['source']}] {c['text']}" for i, c in enumerate(chunks)
            )
            if chunks
            else "(none)"
        )
        prompt = tmpl.safe_substitute(domain=st.domain, goal=st.goal, context=context)
        try:
            data = _extract_json(
                router.complete(
                    "specialist.generate",
                    [{"role": "user", "content": prompt}],
                    response_format=_JSON,
                    extra_body=_NO_THINK,
                    temperature=0.2,
                )
            )
            # subtask_id is injected by code, not trusted from the LLM. ExpectedOutcome
            # is Pydantic-locked (extra="forbid") — Hard Constraint #13.
            result = SpecialistResult(
                subtask_id=st.subtask_id,
                diagnosis=str(data["diagnosis"]),
                expected_outcome=ExpectedOutcome.model_validate(data["expected_outcome"]),
            )
            log.info(
                "generate", subtask_id=st.subtask_id, metric=result.expected_outcome.target_metric
            )
            return {"final_diagnosis": result}
        except (
            RouterExhausted,
            ValidationError,
            ValueError,
            KeyError,
            json.JSONDecodeError,
        ) as exc:
            # generate is mandatory cloud; there is no safe local/numeric fallback for a
            # typed diagnosis. Surface None → the wrapper escalates (Tier 3 / replan).
            log.error("generate_failed", subtask_id=st.subtask_id, error=str(exc))
            return {"final_diagnosis": None}

    return generate


def _route_after_grade(state: SpecialistState) -> str:
    if state.sufficient or state.rewrite_count >= MAX_REWRITES:
        return "generate"
    return "rewrite"


def build_specialist_nodes(router: Router) -> dict[str, Any]:
    """The five node callables, built once over the shared Router. Exposed so
    eval/runner.py can drive ONE node in isolation (grade / rewrite probes, and the
    ablate checks in ops/llm_routing.md) without invoking the whole subgraph — these
    are the SAME instances the compiled graph registers, never a parallel copy."""
    return {
        "decompose": _make_decompose(router),
        "retrieve": _make_retrieve(),
        "grade": _make_grade(router),
        "rewrite": _make_rewrite(router),
        "generate": _make_generate(router),
    }


def build_specialist_subgraph(router: Router, nodes: dict[str, Any] | None = None) -> Any:
    """Compile the shared 5-node subgraph. Call ONCE at module load. `nodes` lets the
    caller pass a pre-built set (so the compiled graph and the exported single-node
    handles share one instance); defaults to a fresh set."""
    nodes = nodes if nodes is not None else build_specialist_nodes(router)
    g = StateGraph(SpecialistState)
    for name, fn in nodes.items():
        g.add_node(name, fn)

    g.add_edge(START, "decompose")
    g.add_edge("decompose", "retrieve")
    g.add_edge("retrieve", "grade")
    g.add_conditional_edges(
        "grade", _route_after_grade, {"rewrite": "rewrite", "generate": "generate"}
    )
    g.add_edge("rewrite", "retrieve")
    g.add_edge("generate", END)
    return g.compile()


# Compiled once at import (CLAUDE.md: subgraphs compile at module-load, not per-incident).
# SPECIALIST_NODES holds the same node callables the graph registers — exported for the
# bench's single-node probes (grade / rewrite).
_ROUTER = Router()
SPECIALIST_NODES = build_specialist_nodes(_ROUTER)
SPECIALIST_SUBGRAPH = build_specialist_subgraph(_ROUTER, SPECIALIST_NODES)


def run_specialist(payload: dict[str, Any], domain: str) -> dict[str, Any]:
    """Parent-graph entry point shared by the four {domain}.py wrapper NODES.

    Fed by the dispatch fan-out as a LangGraph `Send(domain, {"subtask": ...})`, so
    `payload` is the Send arg (the parent state is NOT visible here — by design,
    one isolated subtask per parallel branch). Runs the shared subgraph on this
    subtask's HYDRATED goal and lifts ONLY `final_diagnosis` back; the subgraph's
    bulky state (retrieved_chunks, grade_reason, rewrite_count) never enters the
    parent checkpoint (🔴 Phase 2 risk #2).

    Status is deliberately NOT written here: parallel branches writing the same
    non-reducer `status` channel would be a concurrent-update error. Success writes
    `subtask_results` (merge reducer); failure appends to `failed_subtasks`
    (add reducer) so the dispatch loop counts it resolved and stops re-dispatching.
    The critic node sets status once after the wave (Phase 2-next: route failures
    to replan / Tier 3 instead of proceeding)."""
    raw = payload["subtask"]
    subtask = raw if isinstance(raw, Subtask) else Subtask.model_validate(raw)
    # Run on the hydrated goal (ReWOO refs already resolved by hydrate_placeholders).
    child = subtask.model_copy(update={"goal": subtask.effective_goal})
    out = SPECIALIST_SUBGRAPH.invoke({"subtask": child})
    diagnosis = out["final_diagnosis"] if isinstance(out, dict) else out.final_diagnosis
    if diagnosis is None:
        log.error("specialist_no_diagnosis", domain=domain, subtask_id=subtask.subtask_id)
        return {"failed_subtasks": [subtask.subtask_id]}
    log.info("specialist_done", domain=domain, subtask_id=subtask.subtask_id)
    return {"subtask_results": {subtask.subtask_id: diagnosis}}
