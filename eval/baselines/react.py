"""Naive single-agent ReAct baseline — the contrast system for IEQ-Bench.

One LLM (deepseek-v4-flash, same base model as IEQ-Ops) in a hand-written
thought→action→observation loop over the same MCP tools. NO langchain
(`create_react_agent` is banned, CLAUDE.md #6/#7) — the loop is explicit so the
baseline is fully inspectable and reproducible.

Deliberately absent (this is the point of the comparison): no planner/DAG, no
domain specialist isolation, no Agentic-RAG self-reflection loop, no critic gate,
no memory recall. Same model, same tools — only the architecture differs, so the
IEQ-Ops − baseline gap on IEQ-Bench is attributable to the architecture, not the
model. A GPT-4o cross-model baseline is added in a later milestone.

To stay comparable to the scored system, `finish` must return the same typed
`expected_outcome` block IEQ-Ops Specialists emit, so the same critic/verifier
scorers apply.

  uv run python -m eval.baselines.react        # demo on a co2 anomaly
"""

from __future__ import annotations

import json
from typing import Any

from openai import OpenAI, OpenAIError

from core.config import get_settings
from core.logging import get_logger
from mcp_servers.actuator.server import mcp as actuator_server
from mcp_servers.client import call_tool
from mcp_servers.rag.server import mcp as rag_server
from mcp_servers.sensor.server import mcp as sensor_server

log = get_logger("baseline-react")

# deepseek v4 returns reasoning_content; disable thinking for stable JSON.
# DEEPSEEK-SPECIFIC — drop when the baseline gains a GPT-4o variant.
_NO_THINK: dict[str, Any] = {"thinking": {"type": "disabled"}}


def _tool_read_sensors(_: dict[str, Any]) -> Any:
    return call_tool(sensor_server, "read_sensors")


def _tool_retrieve(args: dict[str, Any]) -> Any:
    chunks = call_tool(
        rag_server,
        "retrieve",
        query=args.get("query", ""),
        domain=args.get("domain", "airquality"),
        top_k=3,
    )
    return [{"source": c.source, "text": c.text} for c in chunks]


def _tool_set_ventilation(args: dict[str, Any]) -> Any:
    return call_tool(
        actuator_server,
        "set_ventilation",
        level=args.get("level", "medium"),
        reason=args.get("reason", "baseline action"),
    )


# tool name → (one-line description for the prompt, callable)
TOOLS: dict[str, tuple[str, Any]] = {
    "read_sensors": ("read all current sensor values (no args)", _tool_read_sensors),
    "retrieve_standards": (
        'retrieve standards excerpts; args {"query": str, "domain": '
        "co2|airquality|thermal|lighting|acoustic}",
        _tool_retrieve,
    ),
    "set_ventilation": (
        'set ventilation; args {"level": off|low|medium|high, "reason": str}',
        _tool_set_ventilation,
    ),
}


def _system_prompt(max_steps: int) -> str:
    tool_lines = "\n".join(f"  - {name}: {desc}" for name, (desc, _) in TOOLS.items())
    return (
        "You are a building indoor-environmental-quality (IEQ) operations agent. "
        "Diagnose and resolve ONE sensor anomaly using the ReAct pattern.\n\n"
        f"Available tools:\n{tool_lines}\n\n"
        "Each turn output STRICT JSON, exactly one of:\n"
        '  {"thought": "<reasoning>", "action": {"tool": "<name>", "args": {...}}}\n'
        '  {"thought": "<reasoning>", "finish": {"diagnosis": "<grounded text>", '
        '"expected_outcome": {"target_metric": "co2|temperature|humidity|lux|noise_db", '
        '"target_value": <number>, "target_time_min": <int>}}}\n\n'
        "Investigate with tools first (read sensors, retrieve the relevant standard), "
        "act if a corrective tool applies, then finish with a diagnosis grounded in what "
        f"you retrieved and a typed expected_outcome. Use at most {max_steps} steps."
    )


def _execute(tool: str, args: dict[str, Any]) -> Any:
    entry = TOOLS.get(tool)
    if entry is None:
        return {"error": f"unknown tool {tool!r}; available: {list(TOOLS)}"}
    try:
        return entry[1](args)
    except Exception as exc:  # noqa: BLE001 — agent may call a tool wrong; never crash the loop
        return {"error": f"{type(exc).__name__}: {exc}"}


class ReActBaseline:
    """A single LLM looping thought→action→observation over the MCP tools."""

    def __init__(self, model: str | None = None, max_steps: int = 6) -> None:
        s = get_settings()
        self.model = model or s.deepseek_model_flash
        self.client = OpenAI(api_key=s.deepseek_api_key, base_url=s.deepseek_base_url)
        self.max_steps = max_steps

    def run(self, anomaly: dict[str, Any]) -> dict[str, Any]:
        """Drive the loop on one anomaly. Returns {final, steps, trace} where `final`
        is the finish payload ({diagnosis, expected_outcome}) or None if it never
        finished within max_steps."""
        messages: list[dict[str, str]] = [
            {"role": "system", "content": _system_prompt(self.max_steps)},
            {"role": "user", "content": f"Anomaly: {json.dumps(anomaly)}. Diagnose and act."},
        ]
        trace: list[dict[str, Any]] = []
        for step in range(self.max_steps):
            try:
                raw = (
                    self.client.chat.completions.create(
                        model=self.model,
                        messages=messages,  # type: ignore[arg-type]
                        response_format={"type": "json_object"},
                        extra_body=_NO_THINK,
                        temperature=0.2,
                    )
                    .choices[0]
                    .message.content
                    or "{}"
                )
                data = json.loads(raw)
            except (OpenAIError, json.JSONDecodeError) as exc:
                log.warning("baseline_llm_error", step=step, error=str(exc))
                break
            if "finish" in data:
                log.info("baseline_finish", step=step)
                return {"final": data["finish"], "steps": step + 1, "trace": trace}
            action = data.get("action") or {}
            tool, args = action.get("tool", ""), action.get("args", {})
            obs = _execute(tool, args if isinstance(args, dict) else {})
            trace.append({"thought": data.get("thought", ""), "tool": tool, "obs": obs})
            log.info("baseline_step", step=step, tool=tool)
            messages.append({"role": "assistant", "content": raw})
            messages.append(
                {"role": "user", "content": f"Observation: {json.dumps(obs, default=str)[:800]}"}
            )
        return {"final": None, "steps": self.max_steps, "trace": trace, "note": "no finish"}


def main() -> None:
    from core.logging import configure_logging

    configure_logging(get_settings().log_level)
    anomaly = {
        "anomaly": True,
        "sensor": "co2",
        "value": 1300.0,
        "rule_violated": "co2 must stay <= 1000 ppm",
    }
    out = ReActBaseline().run(anomaly)
    print(json.dumps(out, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
