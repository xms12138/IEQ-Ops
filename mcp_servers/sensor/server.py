"""mcp-sensor-server — FastMCP, the single read primitive for every sensor.

read_sensors has three data sources (see the function docstring): the simulator (dev +
injected demos), the latest calibrated hardware row in sensor_readings (the live exhibit),
and the simulator again while an injection-override is in flight. The tool contract (name +
output shape) is fixed, so the Monitor and Verifier are unaffected by which source is
active. No LLM here — this is a pure data primitive.
"""

from __future__ import annotations

from fastmcp import FastMCP

from core.config import get_settings
from sensing.history import latest_reading
from sensing.override import is_active as override_is_active
from sensing.simulator import get_room

mcp = FastMCP("mcp-sensor-server")


@mcp.tool
def read_sensors() -> dict[str, float]:
    """Return the current reading of every sensor, keyed to sensing/thresholds.py.

    Source priority:
      1. injection-override active → the simulator. A presenter's injected demo runs the
         full closed loop on the simulated world (inject + mock actuator + Verifier all
         operate there); see sensing/override.
      2. sensor_source == "hardware" → the latest CALIBRATED row in sensor_readings, written
         by sensing/ingest from the Arduino MKR1010 over MQTT.
      3. otherwise (sim — the dev default) → the simulator's RoomState.
    """
    if override_is_active():
        return get_room().read_all()
    if get_settings().sensor_source == "hardware":
        return latest_reading()
    return get_room().read_all()
