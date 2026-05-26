"""Single-zone CO2 mass-balance simulator — the Phase 1 data source.

Drives the AirQuality vertical slice end to end: it starts in an anomalous
state (high occupancy + low fresh-air flow) so the Monitor fires, and an
actuator raising the ventilation pulls CO2 back down so the Verifier sees a
real improvement 15 simulated minutes later.

Model — CO2 volume balance, ppm form, Euler-integrated:

    dC/dt = [N * E * 1e6 + Q * (C_out - C)] / V

  C    indoor CO2 (ppm)         N  occupancy (persons)
  E    CO2 per person (m3/h)    Q  fresh-air flow (m3/h)
  V    room volume (m3)         C_out  outdoor CO2 (ppm)

Steady state  C_ss = C_out + N*E*1e6 / Q : low Q drives an anomaly, a high-Q
actuator action drives recovery.

Two deliberate Phase 1 choices, both to make the cross-restart test deterministic:
* Time advances only via explicit advance_minutes(), never from wall-clock. The
  run harness advances the room by ExpectedOutcome.target_time_min just before
  the Verifier reads, so "15 minutes later" is exact, not flaky.
* Room state is persisted to a JSON file (IEQ_SIM_STATE). The physical world is
  durable; the simulator stands in for it, so its state must survive the process
  kill that the 15-min suspend/resume test performs. Without this the resumed
  process would read a reset room instead of the post-action high-ventilation one.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

OUTDOOR_CO2 = 420.0  # ppm, typical outdoor baseline
CO2_PER_PERSON_M3H = 0.018  # pure CO2 exhaled by a seated adult (~0.005 L/s)

_STATE_PATH = Path(os.getenv("IEQ_SIM_STATE", "/tmp/ieq_sim_state.json"))


@dataclass
class CO2Room:
    """One ventilated room. Mutated by the actuator (set_ventilation), read by
    the sensor server (read_co2), advanced explicitly by the run harness."""

    volume_m3: float = 50.0
    occupancy: int = 5
    ventilation_m3h: float = 60.0  # low → steady state ~1920 ppm → anomaly
    co2_ppm: float = 1300.0  # start already above the 1000 ppm rule

    def advance_minutes(self, minutes: float) -> None:
        """Integrate the balance ODE forward by `minutes` simulated minutes."""
        if minutes <= 0:
            return
        steps = max(1, int(round(minutes)))  # ~1-minute Euler steps; stable for our Q/V
        dt_h = (minutes / steps) / 60.0
        for _ in range(steps):
            dcdt = (
                self.occupancy * CO2_PER_PERSON_M3H * 1e6
                + self.ventilation_m3h * (OUTDOOR_CO2 - self.co2_ppm)
            ) / self.volume_m3
            self.co2_ppm = max(OUTDOOR_CO2, self.co2_ppm + dcdt * dt_h)

    def read_co2(self) -> float:
        return round(self.co2_ppm, 1)

    def set_ventilation(self, m3h: float) -> None:
        self.ventilation_m3h = m3h


_room: CO2Room | None = None


def get_room() -> CO2Room:
    """Process-wide singleton, hydrated from the persisted state file if present
    (so a resumed process recovers the post-action room, not a reset one)."""
    global _room
    if _room is None:
        if _STATE_PATH.exists():
            _room = CO2Room(**json.loads(_STATE_PATH.read_text(encoding="utf-8")))
        else:
            _room = CO2Room()
    return _room


def save_room() -> None:
    """Persist the current room so it survives a process restart."""
    if _room is not None:
        _STATE_PATH.write_text(json.dumps(asdict(_room)), encoding="utf-8")


def reset_room() -> CO2Room:
    """Re-arm the anomaly scenario and persist it (used at the start of a run)."""
    global _room
    _room = CO2Room()
    save_room()
    return _room
