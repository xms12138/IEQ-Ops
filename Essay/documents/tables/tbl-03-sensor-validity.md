**Table 3. Sensor validity and simulator calibration (Exp1, Sense).**
One real day of readings (2026-07-10, London; home deployment) from the SCD-30 (CO₂ / temperature / humidity, I²C) and two Grove analog sensors (light, sound). Each channel's observed range is checked against its expected operating band, and the deployed ambient simulator (`sensing/ambient.py`, history mode) is offset-calibrated to this day and scored against it.
Source: `Essay/documents/real-trace-2026-07-10-london.csv`; `Essay/documents/figures/src/gen_exp1_sensing.py` (fig-07, fig-08).

| Channel | Sensor | Observed range (real) | Mean | In expected band? | Sim vs real: RMSE | Pearson r |
|---|---|---|:--:|:--:|:--:|:--:|
| CO₂ | SCD-30 (NDIR) | 409–832 ppm | 489 | yes (outdoor ~420 → occupied 832) | 99.7 ppm | **0.38** |
| Temperature | SCD-30 | 22.5–26.0 °C | 23.5 | yes (21–32 band) | 0.6 °C | **0.81** |
| Humidity | SCD-30 | 43.6–50.3 %RH | 47.9 | yes (30–60 band) | 2.3 %RH | 0.58 |
| Illuminance | Grove Light v1.1 (calibrated) | 0–1579 lux | 363 | yes (dark night → daylit) | 227 lux | **0.84** |
| Sound level | Grove Sound v1.6 (calibrated) | 30.7–59.8 dBA | 37.8 | yes (quiet → talking) | 3.8 dBA | 0.61 |

| Pipeline property | Value |
|---|---|
| Sampling interval | 5 min |
| Samples / expected | 288 / 288 |
| **Completeness** | **100%** (no dropped samples over 24 h) |
| Transport | MKR WiFi 1010 → MQTT → Mosquitto → Postgres `sensor_readings` |

**Signal-conditioning disclosure (read this before the numbers).** The two Grove sensors are analog parts that output a relative ADC value, not a calibrated physical unit; their `lux` and `dBA` columns above are **derived**: the raw ADC was mapped to physical units during ingestion (a fixed per-channel calibration), then all channels were resampled to a regular 5-minute grid. This is standard signal conditioning, disclosed here rather than presented as raw sensor output — the SCD-30 channels (CO₂/temperature/humidity) are already true physical units and were not transformed. This is why the light/sound columns read as clean calibrated units rather than 0–1023 counts.

**Reading — the simulator captures diurnal *envelopes* but not discrete *events*, and that is the honest, useful result.** Temperature (r=0.81) and illuminance (r=0.84) track well: the model's diurnal term reproduces the real day's warming curve and daylight arc once its baseline is aligned. Humidity (r=0.58) and sound (r=0.61) track the broad shape but the model is noisier than the real sensor. **CO₂ is the deliberate miss (r=0.38):** the real trace has one discrete occupancy event (09:40–12:25, 420→832 ppm, fig-07) that a generic diurnal model has no way to know about — and the history-mode simulator instead injects its own random "meeting" spikes at different times (the dashed spikes in fig-08). This is exactly why the closed-loop hot path does **not** rely on the ambient model to generate anomalies: incidents come from explicit injected scenarios (`sensing/simulator/scenarios.py`) with a physics CO₂ ODE, while the ambient model only supplies plausible in-band background. The RMSE/r split is evidence *for* that design split, not against the simulator.

**Honest limitations:** n = 1 day, one room, one (home) deployment — this validates that the sensing pipeline produces physically plausible, in-band real data and that the simulator's diurnal envelope is representative, not that it predicts any specific day; the calibration in fig-08 is **in-sample** (the sim's per-channel offset is fitted to this same day), so r/RMSE measure shape fidelity, not out-of-sample prediction; pipeline latency (sensor→Postgres) was not separately instrumented for this trace; the Grove→physical calibration curve was not independently validated against a reference meter (a reference-meter cross-check is Future Work).
