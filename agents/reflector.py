"""ReflectorAgent — weekly consolidation; nodes reflector.semantic (#7) +
reflector.procedural (#8) in ops/llm_routing.md.

Cold-path, once a week, inside the ReflectionGraph. Reads a window of closed
episodic trajectories — ONE incident type at a time (the graph fans out by type
so each call sees a bounded slice and stays inside the context window,
ops/llm_routing.md #7 token hazard) — and inducts:

  - reflect_semantic  → building-specific FACTS (generalisations across incidents)
  - reflect_procedural → SOP DRAFTS, from the RESOLVED trajectories only

Both run on the REASONING tier (deepseek-v4-pro) and are MANDATORY cloud — Hard
Constraint #12. Local 8B fabricates generalisations and SOPs wholesale (A4.5), and
the Week-8-vs-Week-1 improvement claim — the dissertation's headline evidence —
rides on the quality of what this distils. Thinking stays ON (unlike the
specialist's JSON nodes): multi-incident induction IS the reasoning task, same as
the planner. On ANY LLM failure these return [] (never a fabricated fact / SOP) and
log a warning — the graph then persists nothing for that type and the operator is
alerted (ops/llm_routing.md #7/#8 fallback: "defer, alert; never local/flash").

The agent only DRAFTS. Id assignment + persistence happen in the memory modules
(semantic.save_facts / procedural.queue_sop), called from the graph's consolidate
node (Hard Constraint #3). Drafts carry no id and SOPs are never active here.
"""

from __future__ import annotations

import json
import re
from typing import Any

from agents.prompt_loader import load_prompt
from core.logging import get_logger
from core.router import Router, RouterExhausted
from memory.episodic import EpisodicCase
from memory.procedural import SOPDraft
from memory.semantic import SemanticFactDraft

log = get_logger("reflector")

_JSON = {"type": "json_object"}


def _extract_json(text: str) -> dict[str, Any]:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError(f"no JSON in response: {text[:120]!r}")
    data: Any = json.loads(m.group(0))
    if not isinstance(data, dict):
        raise ValueError(f"expected a JSON object, got {type(data).__name__}")
    return data


def _render_cases(cases: list[EpisodicCase]) -> str:
    """Compact one-line-per-incident rendering for the reflector prompt. Outcome
    is spelled RESOLVED / FAILED so the model can weigh successes from failures."""
    lines: list[str] = []
    for c in cases:
        outcome = "RESOLVED" if c.verdict == "met" else "FAILED"
        lines.append(
            f"- [{c.incident_id}] room {c.room}, {c.sensor}={c.value} ({c.rule_violated}) "
            f"→ diagnosis: {c.diagnosis} | action: {c.action_taken or 'n/a'} "
            f"→ {outcome} (target {c.target_metric} ≤ {c.target_value})"
        )
    return "\n".join(lines)


class ReflectorAgent:
    def __init__(self, router: Router | None = None) -> None:
        self.router = router or Router()
        self._semantic_tmpl = load_prompt("reflector/semantic")
        self._procedural_tmpl = load_prompt("reflector/procedural")

    def reflect_semantic(
        self, incident_type: str, cases: list[EpisodicCase]
    ) -> list[SemanticFactDraft]:
        """Induct building facts from one type's week of incidents (both resolved
        and failed — a failure teaches a fact too)."""
        if not cases:
            return []
        prompt = self._semantic_tmpl.safe_substitute(
            incident_type=incident_type, n_cases=len(cases), cases=_render_cases(cases)
        )
        try:
            data = _extract_json(
                self.router.complete(
                    "reflector.semantic",
                    [{"role": "user", "content": prompt}],
                    response_format=_JSON,
                    temperature=0.0,
                )
            )
        except (RouterExhausted, ValueError, json.JSONDecodeError) as exc:
            log.warning("reflector_semantic_fallback", incident_type=incident_type, error=str(exc))
            return []
        drafts: list[SemanticFactDraft] = []
        for f in data.get("facts", []):
            if not isinstance(f, dict) or not str(f.get("fact", "")).strip():
                continue
            drafts.append(
                SemanticFactDraft(
                    fact=str(f["fact"]).strip(),
                    incident_type=incident_type,
                    evidence_ids=[str(x) for x in f.get("evidence_ids", []) if str(x).strip()],
                )
            )
        log.info("reflector_semantic", incident_type=incident_type, n_facts=len(drafts))
        return drafts

    def reflect_procedural(self, incident_type: str, cases: list[EpisodicCase]) -> list[SOPDraft]:
        """Draft SOPs from the RESOLVED trajectories of one type (a failed attempt
        is not a procedure to repeat). Drafts are queued PENDING — never active."""
        resolved = [c for c in cases if c.verdict == "met"]
        if not resolved:
            log.info("reflector_procedural_skip", incident_type=incident_type, reason="no resolved")
            return []
        prompt = self._procedural_tmpl.safe_substitute(
            incident_type=incident_type, n_cases=len(resolved), cases=_render_cases(resolved)
        )
        try:
            data = _extract_json(
                self.router.complete(
                    "reflector.procedural",
                    [{"role": "user", "content": prompt}],
                    response_format=_JSON,
                    temperature=0.0,
                )
            )
        except (RouterExhausted, ValueError, json.JSONDecodeError) as exc:
            log.warning(
                "reflector_procedural_fallback", incident_type=incident_type, error=str(exc)
            )
            return []
        drafts: list[SOPDraft] = []
        for s in data.get("sops", []):
            if not isinstance(s, dict):
                continue
            steps = [str(x).strip() for x in s.get("steps", []) if str(x).strip()]
            if not str(s.get("title", "")).strip() or not steps:
                continue
            drafts.append(
                SOPDraft(
                    title=str(s["title"]).strip(),
                    trigger_condition=str(s.get("trigger_condition", "")).strip(),
                    steps=steps,
                    incident_type=incident_type,
                    evidence_ids=[str(x) for x in s.get("evidence_ids", []) if str(x).strip()],
                )
            )
        log.info("reflector_procedural", incident_type=incident_type, n_sops=len(drafts))
        return drafts
