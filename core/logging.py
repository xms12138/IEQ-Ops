"""Structured JSON logging via structlog, forwarded to LangFuse downstream.

`configure_logging()` is called once at process startup. Agents then do:

    log = get_logger("monitor")
    log.info("anomaly", sensor="co2", value=1450, rule_violated="co2>1000")

`merge_contextvars` is the important piece: binding `incident_id` once at the
graph entry (via structlog.contextvars.bind_contextvars) makes every downstream
agent's log line carry it automatically — no threading the field through calls.
This is how the CLAUDE.md log contract {agent, incident_id, plan_id, step,
tokens_in, tokens_out, latency_ms} is satisfied without boilerplate.
"""

import logging

import structlog
from structlog.typing import FilteringBoundLogger


def configure_logging(level: str = "INFO") -> None:
    numeric_level = logging.getLevelNamesMapping().get(level.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", level=numeric_level)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> FilteringBoundLogger:
    return structlog.get_logger(name)  # type: ignore[no-any-return]  # proxy binds to FilteringBoundLogger at runtime
