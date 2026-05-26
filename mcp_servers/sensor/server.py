"""mcp-sensor-server — FastMCP, reads the simulator (Phase 1).

Phase 5 swaps the body of read_sensors to query InfluxDB; the tool contract
(name + output shape) stays fixed so the Monitor and Verifier are unaffected.
No LLM here — this is a pure data primitive.
"""

from __future__ import annotations

from fastmcp import FastMCP

from sensing.simulator import get_room

mcp = FastMCP("mcp-sensor-server")


@mcp.tool
def read_sensors() -> dict[str, float]:
    """Return the current reading of every sensor in the room.

    Phase 1: CO2 comes from the live simulator; the others sit at nominal
    in-band values so only the AirQuality line produces anomalies.
    """
    room = get_room()
    return {
        "co2": room.read_co2(),
        "temperature": 22.5,
        "humidity": 45.0,
        "lux": 420.0,
        "noise_db": 41.0,
    }
