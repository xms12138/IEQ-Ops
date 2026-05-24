"""Postgres checkpointer for LangGraph — the basis of the 15-min suspend/resume.

MainIncidentGraph suspends for 15 minutes between `action` and `verifier`. That
wait must survive a process restart (Phase 1 risk #1), so checkpoints persist to
Postgres rather than memory. The graph is compiled with this saver in core/graph.py.

Lifecycle: `PostgresSaver.from_conn_string` is a context manager that owns the
connection, so the saver is opened around the graph's run, not stored as a global.

    with open_checkpointer() as cp:
        graph = builder.compile(checkpointer=cp)
        graph.invoke(...)

`setup_checkpointer()` creates the checkpoint tables; run it once after Postgres
is first up (Docker not yet installed locally, so this is untested live — Phase 0).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from langgraph.checkpoint.postgres import PostgresSaver

from core.config import get_settings
from core.logging import get_logger

log = get_logger("checkpointer")


@contextmanager
def open_checkpointer() -> Iterator[PostgresSaver]:
    """Open a Postgres-backed checkpointer bound to DATABASE_URL for the duration."""
    with PostgresSaver.from_conn_string(get_settings().database_url) as cp:
        yield cp


def setup_checkpointer() -> None:
    """One-time: create the checkpoint tables. Run after Postgres is up."""
    with open_checkpointer() as cp:
        cp.setup()
    log.info("checkpointer_setup_complete")
