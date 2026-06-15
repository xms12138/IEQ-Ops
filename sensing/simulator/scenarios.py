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
    # Exhibit safety. True = a deterministic single-pass outcome, safe to inject live in front
    # of an audience. False = a replan/FAILED demonstration (co2_overcrowded): kept for the
    # dissertation write-up and CLI runs, but hidden from the exhibit inject panel so a live
    # demo never shows a replan loop or a FAILED incident. Enforced in ops.py (/api/scenarios
    # filters it out, /api/inject rejects it); the demo.py CLI still lists and runs it.
    exhibit_safe: bool = True


SCENARIOS: dict[str, Scenario] = {
    "co2_spike": Scenario(
        name="co2_spike",
        description=(
            "Packed meeting room, under-ventilated — CO2 spikes to 1300 ppm "
            "(full loop: ventilate → recover → close)"
        ),
        expected_sensor="co2",
        expected_domain="airquality",
        closes_loop=True,
        room={"occupancy": 5, "ventilation_m3h": 60.0, "co2_ppm": 1300.0},
    ),
    "co2_overcrowded": Scenario(
        name="co2_overcrowded",
        description=(
            "Sustained overcrowding: 20 people in a 50 m³ room, ventilation already maxed "
            "(450 m³/h) yet CO2 won't drop (steady state ≈1220 ppm). No single actuator can "
            "fix it → the system retries until the budget is spent, then honestly marks FAILED "
            "(demonstrates the replan loop + safety floor)"
        ),
        expected_sensor="co2",
        expected_domain="airquality",
        closes_loop=True,
        # vent already maxed (450) yet C_ss = 420 + 20*0.018e6/450 ≈ 1220 > any sane target,
        # so every 15-min verify still reads ≈1220 → "missed" → replan, deterministically, until
        # MAX_REPLANS is spent. The honest outcome of an anomaly the actuator cannot fix.
        room={"occupancy": 20, "ventilation_m3h": 450.0, "co2_ppm": 1220.0},
        exhibit_safe=False,  # replan→FAILED demo — paper/CLI only, never on the live exhibit panel
    ),
    "overheating": Scenario(
        name="overheating",
        description=(
            "Afternoon west sun + weak HVAC — room temperature climbs to 29°C "
            "(over the 25°C comfort limit)"
        ),
        expected_sensor="temperature",
        expected_domain="thermal",
        closes_loop=False,
        room={"temperature": 29.0},
    ),
    "dim_workspace": Scenario(
        name="dim_workspace",
        description=(
            "Overcast + partial luminaire failure — illuminance drops to 120 lux "
            "(below the 320 lux task requirement)"
        ),
        expected_sensor="lux",
        expected_domain="lighting",
        closes_loop=False,
        room={"lux": 120.0},
    ),
    "noisy_room": Scenario(
        name="noisy_room",
        description=(
            "Construction noise next door — 68 dBA indoors "
            "(over the 50 dBA office background limit)"
        ),
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


# sensor name (AnomalyRecord / read_all key) → the RoomState field that holds it.
_SENSOR_FIELD: dict[str, str] = {
    "co2": "co2_ppm",
    "temperature": "temperature",
    "humidity": "humidity",
    "lux": "lux",
    "noise_db": "noise_db",
}


def arm_value(sensor: str, value: float) -> None:
    """Install a room with `sensor` reading exactly `value` (every other sensor at its
    in-band default). Used by the e2e bench so a baseline's read_sensors agrees with the
    anomaly it was handed — fair for ANY task value, not only the fixed named scenarios
    (which arm one hard-coded reading each). read_co2() returns the stored value without
    advancing physics, so the reading does not drift before the baseline reads it."""
    field = _SENSOR_FIELD.get(sensor)
    if field is None:
        return
    overrides: dict[str, float] = {field: value}
    if sensor == "co2":
        # hold CO2 high across the read (low outdoor air) — matches the co2_spike scenario.
        overrides["ventilation_m3h"] = 60.0
    set_active_room(RoomState(**overrides))
