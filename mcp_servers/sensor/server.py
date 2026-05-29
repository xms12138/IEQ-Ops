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

    All readings come from the simulator's RoomState: CO2 evolves under the
    mass-balance model, the other three domains hold whatever the active
    scenario injected (in band by default). Phase 5 swaps the body for InfluxDB.
    """
    return get_room().read_all()
