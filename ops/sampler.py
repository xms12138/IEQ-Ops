"""ops/sampler.py — lightweight history sampler for the Q&A butler.

The ONLY long-running process in the Q&A-first MVP. Every SAMPLE_INTERVAL_SECONDS
it reads all sensors via mcp-sensor-server and appends one row to sensor_readings
(sensing.history.record_reading). It does NOT run the incident graph — it only
grows the time series the ConversationalAgent queries for statistical questions.

    python -m ops.sampler        # SAMPLE_INTERVAL_SECONDS=10 for a fast demo trend

Phase 5: when the 5-min monitoring loop goes live it reuses the same
record_reading; sampling can fold into the monitor scan or stay independent.
"""

from __future__ import annotations

from apscheduler.schedulers.blocking import BlockingScheduler

from core.config import get_settings
from core.logging import get_logger
from mcp_servers.client import call_tool
from mcp_servers.sensor.server import mcp as sensor_server
from mcp_servers.ticket.server import init_schema
from sensing.history import record_reading

log = get_logger("sampler")


def sample_once() -> None:
    """One sampling tick: read all sensors → append a sensor_readings row."""
    readings = call_tool(sensor_server, "read_sensors")
    record_reading(readings)


def main() -> None:
    init_schema()  # ensure sensor_readings exists before the first tick
    interval = get_settings().sample_interval_seconds
    log.info("sampler_start", interval_seconds=interval)
    sample_once()  # fire one immediately so the table isn't empty until interval 1
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(sample_once, "interval", seconds=interval, max_instances=1, coalesce=True)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("sampler_stop")


if __name__ == "__main__":
    main()
