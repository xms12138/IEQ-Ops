"""Named demo scenarios — the dev/stage way to inject an anomaly.

A scenario is one set of RoomState overrides plus the domain it should route to.
This generalises the single hard-coded anomaly that used to live in
reset_room(): the demo runner arms a scenario by name, the Monitor reads the
injected readings, and the incident flows to the matching Specialist.

Why each non-CO2 scenario overrides exactly ONE sensor: RoomState defaults are
all in band, so the Monitor only fires on the sensor a scenario pushes out of
band. If a thermal scenario left CO2 at an anomalous value, the Monitor would
trip on CO2 first (it is checked before temperature) and route to airquality
instead — the scenario would silently test the wrong domain. Keeping CO2 (and
every other sensor) at its in-band default isolates the domain under test.

Phase 2 scope: only SUDDEN-SPIKE scenarios (a value already past the threshold
at t=0). Gradual degradation and recurring patterns (which need Phase 3 memory
to be meaningful) come later — see EXECUTION_PLAN.md.

Only the airquality scenario runs the full closed loop (actuator + Verifier);
the other three have no actuator until Phase 5, so the demo runner shows them
through diagnosis + critic and stops at the autonomy gate's Tier 3 interrupt.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sensing.simulator.room import RoomState, set_active_room


@dataclass(frozen=True)
class Scenario:
    """One injectable anomaly. `room` holds RoomState field overrides; every
    field left out keeps its in-band default, so only the target sensor trips."""

    name: str
    description: str  # human-facing one-liner, shown by the demo runner
    expected_sensor: str  # which sensor the Monitor should flag
    expected_domain: str  # which Specialist the incident should route to
    closes_loop: bool  # True only for airquality (has actuator + Verifier)
    room: dict[str, float] = field(default_factory=dict)


SCENARIOS: dict[str, Scenario] = {
    "co2_spike": Scenario(
        name="co2_spike",
        description="满员会议室通风不足,CO2 冲到 1300ppm(完整闭环:通风→恢复→关单)",
        expected_sensor="co2",
        expected_domain="airquality",
        closes_loop=True,
        room={"occupancy": 5, "ventilation_m3h": 60.0, "co2_ppm": 1300.0},
    ),
    "overheating": Scenario(
        name="overheating",
        description="午后西晒 + HVAC 不足,室温升到 29°C(超 26°C 热舒适上限)",
        expected_sensor="temperature",
        expected_domain="thermal",
        closes_loop=False,
        room={"temperature": 29.0},
    ),
    "dim_workspace": Scenario(
        name="dim_workspace",
        description="阴天 + 部分灯具故障,照度跌到 120lux(低于 300lux 工作面要求)",
        expected_sensor="lux",
        expected_domain="lighting",
        closes_loop=False,
        room={"lux": 120.0},
    ),
    "noisy_room": Scenario(
        name="noisy_room",
        description="隔壁施工噪声穿透,室内 68dBA(超 55dBA 办公上限)",
        expected_sensor="noise_db",
        expected_domain="acoustic",
        closes_loop=False,
        room={"noise_db": 68.0},
    ),
}


def scenario_names() -> list[str]:
    return list(SCENARIOS)


def arm(name: str) -> Scenario:
    """Install the named scenario as the active room (persisted) and return it.
    Raises KeyError for an unknown name — the demo runner surfaces the list."""
    sc = SCENARIOS[name]
    set_active_room(RoomState(**sc.room))
    return sc
