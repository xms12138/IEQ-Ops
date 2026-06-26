"""sensing/calibration.py — raw hardware frame → engineering-unit reading.

The Arduino MKR1010 publishes a raw MQTT frame: the SCD30 gives co2 / temperature /
humidity in real units, but the two Grove analog sensors give light_raw / sound_raw as
0–1023 ADC counts with no physical meaning. This module turns one raw frame into the
sensor_readings shape (sensing.history.SENSOR_COLUMNS) the rest of the system speaks:

  * temperature   — minus the SCD30 self-heating offset (settings.temp_offset_c)
  * lux           — light_raw mapped by two-point linear interpolation
  * noise_db      — sound_raw mapped by two-point linear interpolation
  * co2 / humidity — passed through (SCD30 absolute values)

Until a light/sound channel's two raw extremes are measured (lo == hi, the default), that
channel is UNCALIBRATED: a raw count cannot be trusted as lux/dBA, so we return an in-band
SAFE value rather than a fabricated number — the Monitor must not raise a lux or noise
anomaly off an unmapped count. Fill the extremes in .env and the channel goes live with no
code change. No LLM here — pure arithmetic.
"""

from __future__ import annotations

from core.config import Settings, get_settings

# In-band stand-ins for an uncalibrated light/sound channel. They match the simulator's
# RoomState defaults (lux band is >= 320, noise band is <= 50), so they never trip the
# Monitor while a channel is still unmapped.
SAFE_LUX = 420.0
SAFE_NOISE_DB = 41.0

_EPS = 1e-6


def _two_point(
    raw: float, raw_lo: float, raw_hi: float, y_lo: float, y_hi: float, safe: float
) -> float:
    """Linear map raw→y through two measured points, or `safe` when uncalibrated (the two
    raw extremes coincide). Floored at 0 — lux and dBA are non-negative."""
    if abs(raw_hi - raw_lo) < _EPS:
        return safe  # uncalibrated — no trustworthy mapping yet
    y = y_lo + (raw - raw_lo) * (y_hi - y_lo) / (raw_hi - raw_lo)
    return round(max(0.0, y), 1)


def calibrate(frame: dict[str, float], settings: Settings | None = None) -> dict[str, float]:
    """One raw MQTT frame → a reading dict keyed to SENSOR_COLUMNS.

    `frame` carries co2 / temperature / humidity / light_raw / sound_raw (the firmware's
    JSON). Missing keys are skipped, so a partial frame still records what it has."""
    s = settings or get_settings()
    out: dict[str, float] = {}
    if "co2" in frame:
        out["co2"] = round(float(frame["co2"]), 1)
    if "temperature" in frame:
        out["temperature"] = round(float(frame["temperature"]) - s.temp_offset_c, 1)
    if "humidity" in frame:
        out["humidity"] = round(float(frame["humidity"]), 1)
    if "light_raw" in frame:
        out["lux"] = _two_point(
            float(frame["light_raw"]),
            s.light_raw_dark,
            s.light_raw_bright,
            s.light_lux_dark,
            s.light_lux_bright,
            SAFE_LUX,
        )
    if "sound_raw" in frame:
        out["noise_db"] = _two_point(
            float(frame["sound_raw"]),
            s.sound_raw_quiet,
            s.sound_raw_loud,
            s.sound_db_quiet,
            s.sound_db_loud,
            SAFE_NOISE_DB,
        )
    return out
