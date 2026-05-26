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
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from core.config import get_settings
from core.logging import get_logger

log = get_logger("checkpointer")

# core.state Pydantic types that travel through the checkpoint. Listed explicitly
# so the msgpack deserializer ALLOWS them rather than falling back to LangGraph's
# permissive "allow all, warn" default — which it has announced it will block in a
# future version. LangGraph's own SAFE_MSGPACK_TYPES stay allowed unconditionally;
# this allowlist only governs our types. Add any new state type here in Phase 2+.
_CHECKPOINT_TYPES: list[tuple[str, ...]] = [
    ("core.state", name)
    for name in (
        "AnomalyRecord",
        "ExpectedOutcome",
        "Subtask",
        "Plan",
        "SpecialistResult",
        "CriticVerdict",
        "VerifierVerdict",
        "MainIncidentState",
    )
]


def _serde() -> JsonPlusSerializer:
    return JsonPlusSerializer(allowed_msgpack_modules=_CHECKPOINT_TYPES)


@contextmanager
def open_checkpointer() -> Iterator[PostgresSaver]:
    """Open a Postgres-backed checkpointer bound to DATABASE_URL for the duration.

    The saver's serializer is replaced with one carrying an explicit msgpack
    allowlist for our state types (from_conn_string does not accept a serde)."""
    with PostgresSaver.from_conn_string(get_settings().database_url) as cp:
        cp.serde = _serde()
        yield cp


def setup_checkpointer() -> None:
    """One-time: create the checkpoint tables. Run after Postgres is up."""
    with open_checkpointer() as cp:
        cp.setup()
    log.info("checkpointer_setup_complete")
