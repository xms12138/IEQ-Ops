"""mcp-actuator-server — FastMCP, fake executor in dev (Hard Constraint #2 path).

In dev (ENV=dev) "executing" an action means logging it and mutating the
simulator (raising ventilation), which closes the loop so the Verifier sees a
real CO2 drop. In prod this drives the physical device and never touches a
simulator. Either way the call only ever happens AFTER the autonomy gate.
No LLM here.
"""

from __future__ import annotations

from fastmcp import FastMCP

from core.config import get_settings
from core.logging import get_logger
from sensing.simulator import get_room, save_room

log = get_logger("mcp-actuator")
mcp = FastMCP("mcp-actuator-server")

# Discrete actuator settings → fresh-air flow (m3/h). "high" forces recovery:
# steady state C_ss = 420 + 5*0.018e6/450 ≈ 620 ppm, well under the 900 target.
VENTILATION_LEVELS: dict[str, float] = {"off": 10.0, "low": 80.0, "medium": 200.0, "high": 450.0}


@mcp.tool
def set_ventilation(level: str, reason: str) -> dict[str, object]:
    """Set the room's ventilation to a discrete level. `reason` is logged for audit."""
    if level not in VENTILATION_LEVELS:
        raise ValueError(
            f"unknown ventilation level {level!r}; expected {list(VENTILATION_LEVELS)}"
        )
    m3h = VENTILATION_LEVELS[level]
    dev = get_settings().is_dev
    log.info(
        "actuator_set_ventilation",
        level=level,
        target_m3h=m3h,
        reason=reason,
        mode="dev-fake" if dev else "prod-physical",
    )
    if dev:
        get_room().set_ventilation(m3h)
        save_room()  # persist so the post-action room survives the 15-min suspend/restart
    return {"actuator": "ventilation", "level": level, "target_m3h": m3h, "executed": True}
