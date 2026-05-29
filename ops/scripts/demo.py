"""ops.scripts.demo — 展示导向的闭环 runner(Phase 2 验收点)。

与 run_incident.py 共用同一个 build_main_graph(绝不另起平行系统),区别只在于用
graph.stream(stream_mode="updates") 逐节点打印「现在到哪个 agent → state 出现哪些
字段变更 → 该节点产出了什么」,把自主闭环讲清楚(给作者自学,也给现场观众看)。

  uv run python -m ops.scripts.demo --list
  uv run python -m ops.scripts.demo co2_spike       # 完整闭环,关单
  uv run python -m ops.scripts.demo overheating      # 停在 Tier3 挂起(执行层 Phase 5)

airquality 场景跑完整闭环(诊断→critic→Tier1 自动执行→15min 后验证关单);其余三个
domain 没有 actuator(Phase 5),走到 autonomy_gate 时落到 Tier3 阻塞在 interrupt(),
demo 在此优雅收尾,如实呈现系统当前的能力边界。

注意:父图 stream 只看得到 specialist 节点最终吐出的 subtask_results;子图五节点
(decompose/retrieve/grade/rewrite/generate)的 RAG 中间态是隔离的,不进父图(风险
点 #2)。想看子图内部,看 structlog 日志。
"""

from __future__ import annotations

import argparse
import os
import uuid
from typing import Any

from langfuse.decorators import langfuse_context
from pydantic import ValidationError

from core.checkpointer import open_checkpointer
from core.config import get_settings
from core.graph import INTERRUPT_BEFORE, build_main_graph
from core.logging import configure_logging
from core.state import MainIncidentState
from mcp_servers.ticket.server import init_schema
from sensing.simulator import get_room, save_room
from sensing.simulator.scenarios import SCENARIOS, arm, scenario_names

BAR = "=" * 74


# ── pretty-printers ───────────────────────────────────────────────────────────


def _truncate(s: Any, n: int) -> str:
    flat = " ".join(str(s).split())
    return flat if len(flat) <= n else flat[:n] + "…"


def _line(label: str, value: Any) -> None:
    print(f"    {label}: {value}")


def _render_plan(node: str, plan: Any) -> None:
    if plan is None:
        return
    if node == "hydrate_placeholders":
        filled = [st for st in plan.subtasks if st.hydrated_goal and st.hydrated_goal != st.goal]
        if not filled:
            print("    (本波无 ReWOO 占位符待填)")
            return
        for st in filled:
            _line(f"hydrate[{st.subtask_id}]", _truncate(st.hydrated_goal, 200))
        return
    print(f"    ReWOO DAG ({len(plan.subtasks)} 子任务):")
    for st in plan.subtasks:
        deps = f" 依赖{st.depends_on}" if st.depends_on else ""
        print(f"      {st.subtask_id}[{st.domain}]{deps}: {_truncate(st.goal, 150)}")


def _render_field(node: str, key: str, value: Any) -> None:
    if key == "anomaly":
        if value is None:
            return
        if not value.anomaly:
            _line("anomaly", "无异常,所有读数在带内")
        else:
            _line("anomaly", f"⚠ {value.sensor}={value.value} 违反[{value.rule_violated}]")
    elif key == "incident_id":
        _line("incident_id", value)
    elif key == "status":
        _line("status", getattr(value, "value", value))
    elif key == "current_plan":
        _render_plan(node, value)
    elif key == "similar_cases":
        _line("similar_cases", value or "(无 — Phase 3 接 episodic 记忆)")
    elif key == "subtask_results":
        for sid, r in value.items():
            eo = r.expected_outcome
            _line(f"诊断[{sid}]", _truncate(r.diagnosis, 220))
            _line(
                "  期望结果", f"{eo.target_metric}={eo.target_value} 于 {eo.target_time_min}min 内"
            )
    elif key == "failed_subtasks":
        if value:
            _line("failed_subtasks", value)
    elif key == "critic_verdict":
        if value is None:
            return
        tag = "✓ 批准" if value.approved else "✗ 否决(诊断不可信,不执行)"
        extra = f" 未支撑声明={value.unsupported_claims}" if value.unsupported_claims else ""
        _line("critic", tag + extra)
    elif key == "autonomy_tier":
        if value is not None:
            _line("autonomy_tier", f"Tier{int(value)}")
    elif key == "action_taken":
        _line("action_taken", value)
    elif key == "verifier_verdict":
        if value is not None:
            _line("verifier", f"{value.verdict} (delta={value.delta})")
    elif key == "replan_count":
        return  # 不展示
    else:
        _line(key, _truncate(value, 200))


def _render_node(node: str, delta: dict[str, Any]) -> None:
    print(f"\n▶ {node}")
    if not delta:
        print("    (无状态变更 — 纯路由/调度节点)")
        return
    for key, value in delta.items():
        _render_field(node, key, value)


def _stream(graph: Any, graph_input: MainIncidentState | None, config: dict[str, Any]) -> bool:
    """Stream updates, pretty-print every node. Return True if a Tier-3 interrupt fired."""
    interrupted = False
    for chunk in graph.stream(graph_input, config, stream_mode="updates"):
        if "__interrupt__" in chunk:
            intrs = chunk["__interrupt__"]
            if not intrs:
                continue  # 空 tuple = interrupt_before 的静态 suspend(verifier 前),非 Tier3
            interrupted = True
            print("\n⏸ autonomy_gate — Tier 3 interrupt()")
            _line("原因", getattr(intrs[0], "value", intrs[0]))
            continue
        for node, delta in chunk.items():
            _render_node(node, delta)
    return interrupted


def _target_minutes(values: dict[str, Any]) -> int:
    try:
        result = MainIncidentState.model_validate(values).primary_result()
        return result.expected_outcome.target_time_min if result is not None else 15
    except (ValidationError, AttributeError):
        return 15


# ── scenario driver ───────────────────────────────────────────────────────────


def run_scenario(name: str) -> None:
    sc = arm(name)
    print(BAR)
    print(f"场景: {sc.name}  —  {sc.description}")
    print(f"  预期: monitor 触发 {sc.expected_sensor} → 路由 {sc.expected_domain}")
    print(f"  闭环: {'完整(执行→验证→关单)' if sc.closes_loop else 'Tier3 挂起(执行层 Phase 5)'}")
    print(BAR)

    with open_checkpointer() as cp:
        graph = build_main_graph().compile(checkpointer=cp, interrupt_before=INTERRUPT_BEFORE)
        config = {"configurable": {"thread_id": f"demo-{name}-{uuid.uuid4().hex[:8]}"}}

        interrupted = _stream(graph, MainIncidentState(), config)
        snap = graph.get_state(config)

        print("\n" + BAR)
        if interrupted:
            print("结果: 停在 Tier 3 — 该 domain 无 actuator,需人工审批(执行器是 Phase 5)。")
            print("      诊断已产出,如实展示分级自治的能力边界。")
        elif snap.next == ("verifier",):
            mins = _target_minutes(snap.values)
            room = get_room()
            room.advance_minutes(mins)
            save_room()
            print(f"动作已执行,挂起在 verifier 前。模拟推进 {mins} 分钟 →")
            print(f"  {sc.expected_sensor} 现读数 ≈ {room.read_all().get(sc.expected_sensor)}")
            print(BAR)
            _stream(graph, None, config)  # resume from checkpoint → verifier → END
            final = graph.get_state(config)
            verdict = final.values.get("verifier_verdict")
            print("\n" + BAR)
            print(
                f"结果: status={final.values.get('status')} "
                f"verdict={getattr(verdict, 'verdict', None)}"
            )
        else:
            print(f"结果: 提前结束(critic 否决或无异常)status={snap.values.get('status')}")
        print(BAR)


def main() -> None:
    settings = get_settings()
    os.environ.setdefault("LANGFUSE_PUBLIC_KEY", settings.langfuse_public_key)
    os.environ.setdefault("LANGFUSE_SECRET_KEY", settings.langfuse_secret_key)
    os.environ.setdefault("LANGFUSE_HOST", settings.langfuse_host)
    langfuse_context.configure(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
    )
    configure_logging(settings.log_level)
    init_schema()

    parser = argparse.ArgumentParser(description="展示导向的闭环 demo runner(Phase 2)")
    parser.add_argument("scenario", nargs="?", help="场景名(省略或 --list 查看全部)")
    parser.add_argument("--list", action="store_true", help="列出所有可注入场景")
    args = parser.parse_args()

    if args.list or not args.scenario:
        print("可用场景:")
        for n in scenario_names():
            print(f"  {n:14} {SCENARIOS[n].description}")
        return
    if args.scenario not in SCENARIOS:
        print(f"未知场景 {args.scenario!r};可用: {scenario_names()}")
        raise SystemExit(1)

    try:
        run_scenario(args.scenario)
    finally:
        langfuse_context.flush()  # 确保 trace 在进程退出前上传


if __name__ == "__main__":
    main()
