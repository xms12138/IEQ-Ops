"""Run a MainIncidentGraph incident end to end (Phase 1 driver + risk-#1 test).

Subcommands:
  start          arm the simulator, run monitor→…→action, suspend before verifier,
                 print the thread_id (the checkpoint persists in Postgres).
  resume <tid>   advance the simulator by the target window, resume the SAME
                 thread_id → verifier closes (or fails) the incident.
  auto           start + resume in one process (闭环逻辑冒烟).

Cross-restart test (Phase 1 risk #1): run `start` in one process, note the
thread_id, then `resume <tid>` in a FRESH process. The incident continues from
the suspend point because the checkpoint lives in Postgres, not memory.

    uv run python -m ops.scripts.run_incident start
    uv run python -m ops.scripts.run_incident resume I-...-<uuid>
"""

from __future__ import annotations

import argparse
import os
import uuid
from typing import Any

from langfuse.decorators import langfuse_context, observe
from pydantic import ValidationError

from core.checkpointer import open_checkpointer
from core.config import get_settings
from core.graph import INTERRUPT_BEFORE, build_main_graph
from core.logging import configure_logging, get_logger
from core.state import MainIncidentState
from mcp_servers.ticket.server import init_schema
from sensing.simulator import get_room, reset_room, save_room

log = get_logger("run_incident")


def _config(thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}}


def _observe_node(fn: Any, name: str) -> Any:
    """Wrap a graph node so its execution becomes a LangFuse span (no langchain)."""
    return observe(name=name)(fn)


@observe(name="incident_graph")
def _invoke_traced(graph: Any, graph_input: MainIncidentState | None, thread_id: str) -> None:
    """Root trace for the incident. Each node is its own @observe span (see
    _observe_node) and the router's langfuse.openai client nests each LLM call as a
    generation under the active node — all via contextvars, no langchain dependency.
    session_id ties the cross-process start/resume halves into one session."""
    langfuse_context.update_current_trace(session_id=thread_id, name=f"incident:{thread_id}")
    graph.invoke(graph_input, _config(thread_id))


def _target_minutes(values: dict[str, Any]) -> int:
    """Read target_time_min from the PRIMARY (actionable) subtask's expected
    outcome — the one whose domain matches the anomaly, not an arbitrary first
    result, now that a DAG can carry advisory cross-domain subtasks too."""
    try:
        result = MainIncidentState.model_validate(values).primary_result()
        return result.expected_outcome.target_time_min if result is not None else 15
    except (ValidationError, AttributeError):
        return 15


def do_start(thread_id: str) -> None:
    reset_room()  # arm the anomaly scenario and persist it
    with open_checkpointer() as cp:
        graph = build_main_graph(_observe_node).compile(
            checkpointer=cp, interrupt_before=INTERRUPT_BEFORE
        )
        _invoke_traced(graph, MainIncidentState(), thread_id)
        snap = graph.get_state(_config(thread_id))
    print("\n--- SUSPENDED ---")
    print(f"thread_id      = {thread_id}")
    print(f"next (resumes) = {snap.next}")
    print(f"incident_id    = {snap.values.get('incident_id')}")
    print(f"status         = {snap.values.get('status')}")
    print(f"action_taken   = {snap.values.get('action_taken')}")
    print(f"\nresume with:  uv run python -m ops.scripts.run_incident resume {thread_id}")


def do_resume(thread_id: str, minutes: int | None) -> None:
    with open_checkpointer() as cp:
        graph = build_main_graph(_observe_node).compile(
            checkpointer=cp, interrupt_before=INTERRUPT_BEFORE
        )
        snap = graph.get_state(_config(thread_id))
        if not snap.next:
            print(f"thread {thread_id} is not suspended (next={snap.next}); nothing to resume")
            return
        advance = minutes if minutes is not None else _target_minutes(snap.values)
        room = get_room()  # hydrated from the persisted (post-action) room
        room.advance_minutes(advance)
        save_room()
        _invoke_traced(graph, None, thread_id)  # continue from the checkpoint → verifier
        final = graph.get_state(_config(thread_id))
    print("\n--- RESUMED & VERIFIED ---")
    print(f"advanced       = {advance} sim-min")
    print(f"co2 now        = {room.read_co2()} ppm")
    print(f"verdict        = {final.values.get('verifier_verdict')}")
    print(f"status         = {final.values.get('status')}")


def main() -> None:
    settings = get_settings()
    # LangFuse SDK reads keys from the environment; bridge them from typed settings
    # before the lazy client initialises on the first traced call.
    os.environ.setdefault("LANGFUSE_PUBLIC_KEY", settings.langfuse_public_key)
    os.environ.setdefault("LANGFUSE_SECRET_KEY", settings.langfuse_secret_key)
    os.environ.setdefault("LANGFUSE_HOST", settings.langfuse_host)
    # The decorator singleton was already constructed at import (env then unset),
    # so configure it explicitly; this also covers the langfuse.openai client.
    langfuse_context.configure(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
    )
    configure_logging(settings.log_level)
    init_schema()

    parser = argparse.ArgumentParser(description="Run a MainIncidentGraph incident (Phase 1).")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("start")
    p_resume = sub.add_parser("resume")
    p_resume.add_argument("thread_id")
    p_resume.add_argument("--minutes", type=int, default=None)
    sub.add_parser("auto")

    args = parser.parse_args()
    if args.cmd == "start":
        do_start(f"thr-{uuid.uuid4().hex[:12]}")
    elif args.cmd == "resume":
        do_resume(args.thread_id, args.minutes)
    elif args.cmd == "auto":
        tid = f"thr-{uuid.uuid4().hex[:12]}"
        do_start(tid)
        do_resume(tid, None)

    langfuse_context.flush()  # ensure traces upload before the process exits


if __name__ == "__main__":
    main()
