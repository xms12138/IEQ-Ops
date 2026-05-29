"""Run a weekly ReflectionGraph pass (Phase 3 driver; cron wiring is Phase 5).

Consolidates the past week's closed episodic trajectories into semantic facts +
PENDING SOP drafts. Default window = the 7 days ending now; override with
--since / --until (ISO-8601). --week tags the minted SF-/SOP- ids (default: the
current ISO week).

  uv run python -m ops.scripts.run_reflection                 # last 7 days
  uv run python -m ops.scripts.run_reflection --since 2026-05-01  # wider window
  uv run python -m ops.scripts.run_reflection --pending       # just list the SOP queue

SOPs land PENDING — a human signs off before they can drive future handling
(Hard Constraint #8). Review with --pending, then approve/reject in code:
  python -c "from memory.procedural import approve_sop; approve_sop('SOP-2026-001')"
"""

from __future__ import annotations

import argparse
import os
from datetime import UTC, datetime, timedelta
from typing import Any

from langfuse.decorators import langfuse_context, observe

from core.config import get_settings
from core.logging import configure_logging, get_logger
from core.reflection import ReflectionState, build_reflection_graph
from memory.procedural import init_schema as init_sop_schema
from memory.procedural import list_pending

log = get_logger("run_reflection")


def _iso_week(dt: datetime) -> str:
    year, week, _ = dt.isocalendar()
    return f"{year}-W{week:02d}"


def _observe_node(fn: Any, name: str) -> Any:
    """Wrap a graph node as a LangFuse span (same helper as run_incident)."""
    return observe(name=name)(fn)


@observe(name="reflection_graph")
def _invoke_traced(graph: Any, state: ReflectionState) -> dict[str, Any]:
    """Root LangFuse trace for the pass; each Reflector LLM call nests under it via
    the router's langfuse.openai client (same pattern as run_incident)."""
    langfuse_context.update_current_trace(name=f"reflection:{state.week}")
    return graph.invoke(state)


def do_run(week: str, since: str | None, until: str | None) -> None:
    graph = build_reflection_graph(_observe_node)
    out = _invoke_traced(graph, ReflectionState(week=week, since=since, until=until))
    print("\n--- REFLECTION DONE ---")
    print(f"week           = {week}")
    print(f"window         = {since or '(all)'} → {until or 'now'}")
    print(f"episodes read  = {out.get('n_episodes')}")
    print(f"semantic facts = {out.get('saved_fact_ids')}")
    print(f"pending SOPs   = {out.get('queued_sop_ids')}")
    print("\nSOPs are PENDING human sign-off — review with --pending.")


def do_pending() -> None:
    pending = list_pending()
    if not pending:
        print("待签核 SOP 队列为空。")
        return
    print(f"待签核 SOP（{len(pending)} 条）:\n")
    for s in pending:
        print(f"[{s.sop_id}] ({s.incident_type}) {s.title}")
        print(f"  触发: {s.trigger_condition}")
        for i, step in enumerate(s.steps, 1):
            print(f"  {i}. {step}")
        print(f"  证据: {s.evidence_ids}  来源周: {s.source_week}")
        print(
            f'  → 批准: python -c "from memory.procedural import approve_sop; '
            f"approve_sop('{s.sop_id}')\"\n"
        )


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
    init_sop_schema()

    parser = argparse.ArgumentParser(description="Run a weekly ReflectionGraph pass (Phase 3).")
    parser.add_argument("--week", default=None, help="ISO week tag for minted ids (default: now)")
    parser.add_argument("--since", default=None, help="window start, ISO-8601 (default: 7d ago)")
    parser.add_argument("--until", default=None, help="window end, ISO-8601 (default: now)")
    parser.add_argument(
        "--pending", action="store_true", help="list the pending SOP queue and exit"
    )
    args = parser.parse_args()

    if args.pending:
        do_pending()
        return

    now = datetime.now(UTC)
    week = args.week or _iso_week(now)
    since = args.since if args.since is not None else (now - timedelta(days=7)).isoformat()
    try:
        do_run(week, since, args.until)
    finally:
        langfuse_context.flush()  # ensure traces upload before exit


if __name__ == "__main__":
    main()
