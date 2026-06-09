"""core/db.py — one process-wide psycopg connection pool.

Every Postgres access (incidents, sensor_readings, suspended_threads, SOPs) used to open a
fresh psycopg.connect() per call. A long-running deployment hits that constantly — the
monitor scan, the sampler, the scheduler's scan/resume ticks, and every Q&A turn — so each
call paid a connect handshake and nothing bounded the live connection count (the web app
plus the scheduler could exhaust Postgres max_connections under load).

A single lazily-opened pool fixes both: connections are reused, and max_size caps how many
can be live at once. dict_row is configured here so every caller keeps the dict-shaped rows
it already expects. The pool is per-process (web, sampler, scheduler each get their own),
which is correct — they are separate processes.
"""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from core.config import get_settings
from core.logging import get_logger

log = get_logger("db")

# Parameterise the pool to the dict-row connection it actually yields (configured via
# kwargs below) so callers' `_conn() -> Connection[dict[str, Any]]` signatures type-check.
_DictConnPool = ConnectionPool[psycopg.Connection[dict[str, Any]]]

_pool: _DictConnPool | None = None


def get_pool() -> _DictConnPool:
    """The process-wide connection pool, opened on first use. Use as
    `with get_pool().connection() as conn, conn.cursor() as cur: ...` — the connection is
    returned to the pool (not closed) on exit, and the transaction commits as usual."""
    global _pool
    if _pool is None:
        _pool = _DictConnPool(
            conninfo=get_settings().database_url,
            min_size=1,
            max_size=10,
            kwargs={"row_factory": dict_row},
            open=True,
        )
        log.info("db_pool_opened", min_size=1, max_size=10)
    return _pool
