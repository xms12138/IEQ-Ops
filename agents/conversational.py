"""ConversationalAgent — the Q&A butler (ConversationalGraph, MVP slice).

NOT a LangGraph: a single-shot retrieve+synthesise; graphing it would be theater
(same call as memory/episodic being a function, not a node). Two flash calls:

  1. dispatch  — one cheap flash classifies the query into a RetrievalPlan (which
                 BIG sources to pull + domain/sensor/window filters).
  2. synthesis — pull the baseline (current readings + thresholds, ALWAYS) plus
                 only the planned big sources, then one flash grounds an answer in
                 that context and refuses out-of-scope asks.

No RAG / no embedding: range checks ("is the temperature normal?") ride on
sensing.thresholds — the SAME truth the Monitor judges anomalies against — so the
butler never contradicts the system. Both calls are deepseek-v4-flash (router
FAST tier); no V3 escalation in the MVP.
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from agents.prompt_loader import load_prompt
from core.logging import get_logger
from core.router import Router, RouterExhausted
from mcp_servers.client import call_tool
from mcp_servers.sensor.server import mcp as sensor_server
from mcp_servers.ticket.server import mcp as ticket_server
from memory.procedural import active_sops
from memory.semantic import list_facts
from sensing.history import SENSOR_COLUMNS, parse_window, query_stats
from sensing.thresholds import THRESHOLDS

log = get_logger("conversational")

# deepseek v4 is a reasoning model; for structured/short tasks disable thinking or it
# burns the token budget on reasoning_content and may return empty content (P-003).
_NO_THINK: dict[str, Any] = {"extra_body": {"thinking": {"type": "disabled"}}}

# sensor → topic area, to fill `domain` (facts/sops filter) when dispatch gave only a
# sensor, or vice-versa. Mirrors the Monitor's sensor→incident-type grouping.
_SENSOR_DOMAIN = {
    "co2": "airquality",
    "temperature": "thermal",
    "humidity": "thermal",
    "lux": "lighting",
    "noise_db": "acoustic",
}

_DEFAULT_WINDOW = timedelta(days=7)


class RetrievalPlan(BaseModel):
    """What the dispatch flash decides to fetch for one question. The baseline
    (current readings + thresholds) is always pulled, so it is NOT listed here —
    only the bigger, optional sources are gated by these flags."""

    model_config = ConfigDict(extra="forbid")

    need_stats: bool = False
    need_incidents: bool = False
    need_facts: bool = False
    need_sops: bool = False
    sensor: str | None = None  # co2 | temperature | humidity | lux | noise_db
    domain: str | None = None  # airquality | thermal | lighting | acoustic
    since: str | None = None  # window like "30m" / "24h" / "7d"


class ConversationalAgent:
    def __init__(self, router: Router | None = None) -> None:
        self.router = router or Router()
        self._dispatch_tmpl = load_prompt("conversational/dispatch")
        self._respond_tmpl = load_prompt("conversational/respond")

    def respond(self, query: str) -> str:
        """Answer one question: classify → fetch only what's needed → synthesise."""
        plan = self._dispatch(query)
        context = self._gather(plan)
        log.info(
            "conversational_dispatch",
            query=query[:60],
            sources=[
                k for k in ("stats", "incidents", "facts", "sops") if context.get(k) is not None
            ],
        )
        return self._synthesize(query, context)

    def _dispatch(self, query: str) -> RetrievalPlan:
        prompt = self._dispatch_tmpl.safe_substitute(query=query)
        try:
            raw = self.router.complete(
                "conversational.dispatch",
                [{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0,
                **_NO_THINK,
            )
            return RetrievalPlan.model_validate_json(raw)
        except (RouterExhausted, ValidationError, ValueError) as exc:
            log.warning("dispatch_fallback", error=str(exc))
            return RetrievalPlan(need_incidents=True)  # core-source fallback, never stall

    def _gather(self, plan: RetrievalPlan) -> dict[str, Any]:
        # Baseline — always present, tiny, and the basis for any "is X normal?" answer.
        ctx: dict[str, Any] = {
            "current_readings": call_tool(sensor_server, "read_sensors"),
            "thresholds": dict(THRESHOLDS),
        }
        domain = plan.domain or (_SENSOR_DOMAIN.get(plan.sensor) if plan.sensor else None)
        if plan.need_stats:
            sensor = plan.sensor if plan.sensor in SENSOR_COLUMNS else "co2"
            window = parse_window(plan.since, default=_DEFAULT_WINDOW)
            ctx["stats"] = query_stats(sensor, window).model_dump()
        if plan.need_incidents:
            ctx["incidents"] = call_tool(
                ticket_server, "list_incidents", limit=20, sensor=plan.sensor
            )
        if plan.need_facts:
            ctx["facts"] = [f.model_dump() for f in list_facts(incident_type=domain)]
        if plan.need_sops:
            ctx["sops"] = [s.model_dump() for s in active_sops(incident_type=domain)]
        return ctx

    def _synthesize(self, query: str, context: dict[str, Any]) -> str:
        prompt = self._respond_tmpl.safe_substitute(
            query=query,
            context=json.dumps(context, ensure_ascii=False, default=str, indent=2),
        )
        try:
            answer = self.router.complete(
                "conversational.respond",
                [{"role": "user", "content": prompt}],
                temperature=0.3,
                **_NO_THINK,
            )
            return answer.strip()
        except RouterExhausted as exc:
            log.warning("synthesize_failed", error=str(exc))
            return "抱歉,我现在无法连接到推理服务,请稍后再试。"
