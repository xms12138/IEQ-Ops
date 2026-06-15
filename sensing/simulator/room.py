"""Single-zone room-environment simulator — the dev data source for the hot path.

Only CO2 has a physics model (a mass-balance ODE) because airquality is the one
domain with an actuator + Verifier closed loop: raising ventilation must pull CO2
down so the Verifier sees a real improvement 15 simulated minutes later. The other
three domains (thermal / lighting / acoustic) have no actuator until Phase 5, so
their readings are static values a scenario injects out of band to fire the Monitor
— modelling their physics would be code for a requirement that doesn't exist yet.

CO2 model — volume balance, ppm form, Euler-integrated:

    dC/dt = [N * E * 1e6 + Q * (C_out - C)] / V

  C  indoor CO2 (ppm)        N  occupancy (persons)
  E  CO2 per person (m3/h)   Q  fresh-air flow (m3/h)
  V  room volume (m3)        C_out  outdoor CO2 (ppm)

Steady state  C_ss = C_out + N*E*1e6 / Q : low Q drives an anomaly, a high-Q
actuator action drives recovery.

Two deliberate choices, both to keep the cross-restart test deterministic:
* Time advances only via explicit advance_minutes(), never wall-clock. The run
  harness advances the room by ExpectedOutcome.target_time_min just before the
  Verifier reads, so "15 minutes later" is exact, not flaky.
* Room state is persisted to a JSON file (IEQ_SIM_STATE, default <repo>/var/
  sim_state.json — durable disk, NOT /tmp). The physical world is durable; the
  simulator stands in for it, so its state must survive both the process kill that
  the 15-min suspend/resume test performs AND a reboot/power-cut: /tmp is tmpfs (or
  cleared on boot), so a power cut mid-loop would drop the post-action room that the
  resumed Verifier reads back.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

OUTDOOR_CO2 = 420.0  # ppm, typical outdoor baseline
CO2_PER_PERSON_M3H = 0.018  # pure CO2 exhaled by a seated adult (~0.005 L/s)

# Default on durable disk (repo var/), not /tmp — see the module docstring: /tmp does
# not survive a reboot, which would strand a resumed mid-loop incident. IEQ_SIM_STATE
# overrides (e.g. tests point it at a tmp_path).
_DEFAULT_STATE_PATH = Path(__file__).resolve().parents[2] / "var" / "sim_state.json"
_STATE_PATH = Path(os.getenv("IEQ_SIM_STATE", str(_DEFAULT_STATE_PATH)))


@dataclass
class RoomState:
    """One room's full environmental state. CO2 evolves under the mass-balance ODE
    (mutated by the actuator via set_ventilation, advanced by the harness); the
    other three domains are static readings a scenario injects — no actuator drives
    them in Phase 2, so they don't evolve. Defaults are all in band: a scenario
    overrides just the one sensor it wants to push out of band."""

    # CO2 physics — airquality, the only domain with a closed loop in Phase 2.
    volume_m3: float = 50.0
    occupancy: int = 5
    ventilation_m3h: float = 300.0  # default high → steady state ~720 ppm (in band)
    co2_ppm: float = 650.0  # default in band; reset_room() arms the anomaly
    # Static readings for the other three domains — defaults sit safely in band.
    temperature: float = 22.5  # degC — band 21-25
    humidity: float = 45.0  # %RH — band 30-60
    lux: float = 420.0  # lux — must stay >= 320
    noise_db: float = 41.0  # dBA — must stay <= 50

    def advance_minutes(self, minutes: float) -> None:
        """Integrate the CO2 balance ODE forward by `minutes`. Only CO2 evolves;
        the other readings have no actuator driving them and stay put."""
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

    def read_all(self) -> dict[str, float]:
        """Every sensor's current reading, keyed to match sensing/thresholds.py."""
        return {
            "co2": self.read_co2(),
            "temperature": round(self.temperature, 1),
            "humidity": round(self.humidity, 1),
            "lux": round(self.lux, 1),
            "noise_db": round(self.noise_db, 1),
        }


_room: RoomState | None = None


def get_room() -> RoomState:
    """Process-wide singleton, hydrated from the persisted state file if present
    (so a resumed process recovers the post-action room, not a reset one)."""
    global _room
    if _room is None:
        if _STATE_PATH.exists():
            _room = RoomState(**json.loads(_STATE_PATH.read_text(encoding="utf-8")))
        else:
            _room = RoomState()
    return _room


def reload_room() -> RoomState:
    """Drop the cached singleton and re-read the persisted state file, returning the fresh
    room. The simulator file (IEQ_SIM_STATE) is the single source of truth across processes:
    the web process arms a scenario and runs the action (persisting the post-action room),
    while the scheduler process resumes the suspended thread in a SEPARATE process whose
    cached _room would otherwise be stale. Whoever is about to advance physics (the
    scheduler, before the Verifier reads) calls this first so it integrates the latest
    persisted state forward, not its own out-of-date cache."""
    global _room
    _room = None
    return get_room()


def save_room() -> None:
    """Persist the current room so it survives a process restart (and a reboot — the
    default path is on durable disk, not /tmp). Creates the parent dir on first write."""
    if _room is not None:
        _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _STATE_PATH.write_text(json.dumps(asdict(_room)), encoding="utf-8")


def set_active_room(room: RoomState) -> RoomState:
    """Install `room` as the active singleton and persist it. Used by the scenario
    registry to arm a named scenario; reset_room() is the back-compat shortcut."""
    global _room
    _room = room
    save_room()
    return _room


def reset_room() -> RoomState:
    """Re-arm the default CO2 anomaly and persist it (back-compat for
    run_incident.py, which expects reset_room() to fire an airquality incident)."""
    return set_active_room(RoomState(co2_ppm=1300.0, ventilation_m3h=60.0))
