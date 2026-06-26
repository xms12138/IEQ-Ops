"""sensing/override.py — exhibit injection-override marker (cross-process).

Hybrid data model: the exhibit normally reads REAL hardware, but a presenter can inject a
demo anomaly that runs the FULL closed loop. Injection can no longer just mutate the
simulator — read_sensors does not read it under sensor_source == "hardware". So injection
flips this marker instead: while it is active, read_sensors falls back to the simulator
(the world the inject, the mock actuator, and the Verifier all operate on) and the graph
runs the normal Tier-1/Tier-3 loop. When the injected incident reaches a terminal state
the marker is cleared and the exhibit returns to real data.

The marker is a small JSON file (not in-memory) because the WEB process arms it while the
SCHEDULER process reads it — they share no memory, only the Pi's disk. A TTL is a backstop:
if a terminal-state clear is ever missed, the override self-expires so the exhibit cannot
get stuck showing simulated data. No LLM here.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from core.config import get_settings

_DEFAULT_PATH = Path(__file__).resolve().parents[1] / "var" / "override.json"
_PATH = Path(os.getenv("IEQ_OVERRIDE_STATE", str(_DEFAULT_PATH)))

# Backstop lifetime. A demo loop closes in ~90 s (verify_window_seconds); 10 min leaves
# generous room for a Tier-3 approval pause yet guarantees the exhibit self-heals to real
# data if a terminal-state clear is ever missed.
_DEFAULT_TTL_S = 600.0


def activate(sensor: str, ttl_s: float = _DEFAULT_TTL_S) -> None:
    """Enter injection-override for `sensor` — the demo world is simulated until cleared."""
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    _PATH.write_text(
        json.dumps({"sensor": sensor, "armed_at": time.time(), "ttl_s": ttl_s}),
        encoding="utf-8",
    )


def deactivate() -> None:
    """Leave injection-override → read_sensors returns to real hardware. Idempotent."""
    _PATH.unlink(missing_ok=True)


def _read() -> dict[str, Any] | None:
    try:
        data = json.loads(_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def is_active() -> bool:
    """True while an injected demo is in flight. Auto-expires (and clears the file) past TTL."""
    data = _read()
    if data is None:
        return False
    armed_at = float(data.get("armed_at", 0.0))
    ttl_s = float(data.get("ttl_s", _DEFAULT_TTL_S))
    if time.time() - armed_at > ttl_s:
        deactivate()  # self-heal: a missed clear must not strand the exhibit on sim data
        return False
    return True


def active_sensor() -> str | None:
    """The sensor an injected demo is overriding, or None."""
    if not is_active():
        return None
    data = _read()
    return str(data["sensor"]) if data and "sensor" in data else None


def is_live_world() -> bool:
    """True when the system is observing the REAL world: hardware data source AND no
    injection in flight. The graph reads this to choose between the live-observe path
    (diagnose + record, no fake actuator) and the full closed loop (sim/injection, where
    the actuator is effective)."""
    return get_settings().sensor_source == "hardware" and not is_active()


def clear_if_resolved() -> None:
    """Clear injection-override once its sensor no longer has an active incident — i.e. the
    injected demo reached a terminal state. Safe to call from any scan/resume terminal: a
    5-min heartbeat that merely dedups against an in-flight injection leaves the incident
    active, so this never clears mid-demo. Idempotent and TTL-backed. The ticket import is
    deferred so this module stays import-light on read_sensors' hot path."""
    sensor = active_sensor()
    if sensor is None:
        return
    from mcp_servers.client import call_tool
    from mcp_servers.ticket.server import mcp as ticket_server

    if call_tool(ticket_server, "active_incident_for_sensor", sensor=sensor) is None:
        deactivate()
