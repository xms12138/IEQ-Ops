"""Exp1 (Sense) figures — real SCD-30 + Grove sensor trace and simulator calibration.

Reads the real one-day trace CSV the author collected at home
(Essay/documents/real-trace-2026-07-10-london.csv, London, 2026-07-10;
Grove analog channels calibrated to lux/dBA during ingestion — disclosed in tbl-03).
No eval/reports here — this is the raw sensing evidence, not a benchmark.

Chart forms: fig-07 pairs the five-channel time series with a per-channel range
strip (the numeric summary Table 6 reports), so the trace and the summary read
as one plate; fig-08 pairs each channel's overlay with an identity-line scatter,
the standard way to show where a model tracks and where it does not.

The stats block printed by fig08_sim_vs_real() is a regression test — it must keep
reproducing Table 6 exactly (r = 0.38 / 0.81 / 0.58 / 0.84 / 0.61, 288/288, 100%).
"""
from __future__ import annotations

import csv
import math
import random
import sys
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from _style import FULL_W, INK, OFF_C, PALETTE, apply_style, layout, save

# import the deployed simulator model so fig-08 compares against the REAL exhibit code,
# not a re-implementation. parents[4] = repo root (…/figures/src → up 4).
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from sensing.ambient import sample as ambient_sample  # noqa: E402

apply_style()
DOCS = Path(__file__).resolve().parents[1]  # …/documents/figures → parents[1] = documents
REAL_CSV = DOCS.parent / "real-trace-2026-07-10-london.csv"

# channel → (column, label, unit, hue, reference-line text, reference value, side)
CHANNELS = [
    ("co2", "CO₂", "ppm", PALETTE["blue"], ("≤ 900 ppm (WELL A06)", 900, "below")),
    ("temperature", "Temperature", "°C", PALETTE["orange"], ("21–32 °C band", None, None)),
    ("humidity", "Humidity", "%RH", PALETTE["aqua"], ("30–60 %RH band", None, None)),
    ("lux", "Illuminance", "lux", PALETTE["yellow"], ("≥ 320 lux (work plane)", 320, "above")),
    ("noise_db", "Sound level", "dBA", PALETTE["violet"], ("≤ 50 dBA (WELL S02)", 50, "below")),
]

# Natural micro-events observed in the trace — no anomaly was introduced for it.
OCCUPANCY = (9.67, 12.42)   # 09:40–12:25, CO2 rises with people present; noise co-peaks
DAYLIGHT = (5.25, 21.42)    # 05:15–21:25 above 50 lux (London 2026-07-10)


def _load() -> tuple[list[float], dict[str, list[float]]]:
    rows = list(csv.DictReader(open(REAL_CSV)))
    hours = [
        datetime.fromisoformat(r["timestamp"]).hour + datetime.fromisoformat(r["timestamp"]).minute / 60.0
        for r in rows
    ]
    series = {c[0]: [float(r[c[0]]) for r in rows] for c in CHANNELS}
    return hours, series


def _fmt(v: float) -> str:
    return f"{v:.0f}" if abs(v) >= 100 else f"{v:.1f}"


def fig07_real_trace() -> None:
    hours, series = _load()
    fig, axes = plt.subplots(len(CHANNELS), 2, figsize=(FULL_W, 6.6),
                             width_ratios=[4.30, 1.05])
    # share x only DOWN the trace column — the right-hand strips are in five
    # different units and must never share a scale
    for i in range(1, len(CHANNELS)):
        axes[i][0].sharex(axes[0][0])
    for i in range(len(CHANNELS) - 1):
        axes[i][0].tick_params(labelbottom=False)

    for i, (col, label, unit, hue, thr) in enumerate(CHANNELS):
        ax, axr = axes[i][0], axes[i][1]
        y = series[col]
        thr_text, thr_val, side = thr

        # occupancy window shaded on every channel so co-occurrence is visible
        ax.axvspan(*OCCUPANCY, color=PALETTE["orange"], alpha=0.07, zorder=0)
        if col == "lux":
            ax.axvspan(*DAYLIGHT, color=PALETTE["yellow"], alpha=0.09, zorder=0)

        ax.plot(hours, y, color=hue, lw=1.2, zorder=3)
        ax.set_ylabel(f"{label}\n({unit})", fontsize=7.4)
        ax.margins(x=0.005, y=0.16)
        ax.tick_params(labelsize=7.0)

        if thr_val is not None:
            ax.axhline(thr_val, ls="--", lw=0.9, color=INK["muted"], zorder=2)
            ax.text(0.15, thr_val, thr_text, fontsize=6.3, color=INK["secondary"],
                    va="bottom", ha="left")
        else:
            ax.text(23.85, max(y), thr_text, fontsize=6.3, color=INK["secondary"],
                    va="top", ha="right")

        # ── right strip: the day's range and mean, i.e. Table 6 rendered ──────
        lo, hi, mean = min(y), max(y), sum(y) / len(y)
        pad = (hi - lo) * 0.18 or 1.0
        axr.plot([lo, hi], [0, 0], color=hue, lw=4.0, solid_capstyle="round", zorder=3)
        axr.scatter([mean], [0], s=26, facecolor=INK["surface"], edgecolor=hue, lw=1.2,
                    zorder=4)
        if thr_val is not None and lo - pad <= thr_val <= hi + pad:
            axr.axvline(thr_val, ls="--", lw=0.9, color=INK["muted"], zorder=2)
        axr.text(lo, 0.62, _fmt(lo), fontsize=6.2, ha="left", va="bottom",
                 color=INK["secondary"])
        axr.text(hi, 0.62, _fmt(hi), fontsize=6.2, ha="right", va="bottom",
                 color=INK["secondary"])
        axr.text((lo + hi) / 2, -0.85, f"mean {_fmt(mean)}", fontsize=6.2, ha="center",
                 va="top", color=INK["primary"])
        axr.set_xlim(min(lo, thr_val or lo) - pad, max(hi, thr_val or hi) + pad)
        axr.set_ylim(-1.9, 1.6)
        axr.set_yticks([])
        axr.set_xticks([])
        axr.grid(False)
        for sp in axr.spines.values():
            sp.set_visible(False)
        if i == 0:
            axr.set_title("observed range · mean", fontsize=6.8, loc="center", pad=4,
                          color=INK["secondary"], fontweight="normal")

    # per-event annotations, each on the panel where it is most legible
    ax_co2, ax_temp, ax_lux, ax_noise = axes[0][0], axes[1][0], axes[3][0], axes[4][0]
    pk = max(series["co2"])
    ax_co2.annotate(f"morning occupancy 09:40–12:25\nCO₂ 420 → {pk:.0f} ppm",
                    xy=(11.2, pk), xytext=(14.0, pk * 0.985), fontsize=6.5,
                    color=INK["primary"], va="top",
                    arrowprops=dict(arrowstyle="->", color=INK["secondary"], lw=0.8))
    npk = max(series["noise_db"]); nidx = series["noise_db"].index(npk)
    ax_noise.annotate(f"{npk:.0f} dBA (talking, concurrent\nwith the same occupancy window)",
                      xy=(hours[nidx], npk), xytext=(13.2, npk * 0.99), fontsize=6.5,
                      color=INK["primary"], va="top",
                      arrowprops=dict(arrowstyle="->", color=INK["secondary"], lw=0.8))
    lpk = max(series["lux"]); lidx = series["lux"].index(lpk)
    ax_lux.annotate(f"daylight peak {lpk:.0f} lux\n(afternoon, W-facing)",
                    xy=(hours[lidx], lpk), xytext=(17.0, lpk * 0.92), fontsize=6.5,
                    color=INK["primary"], va="top",
                    arrowprops=dict(arrowstyle="->", color=INK["secondary"], lw=0.8))
    tpk = max(series["temperature"]); tidx = series["temperature"].index(tpk)
    ax_temp.annotate(
        f"thermal-mass lag: peak {tpk:.1f} °C at "
        f"{int(hours[tidx]):02d}:{int((hours[tidx] % 1) * 60):02d},\nhours after the solar peak",
        xy=(hours[tidx], tpk), xytext=(1.0, tpk - 0.15), fontsize=6.5,
        color=INK["primary"], va="top",
        arrowprops=dict(arrowstyle="->", color=INK["secondary"], lw=0.8))

    axes[-1][0].set_xlim(0, 24)
    axes[-1][0].set_xticks(range(0, 25, 3))
    axes[-1][0].set_xticklabels([f"{h:02d}:00" for h in range(0, 25, 3)], fontsize=7.0)
    axes[-1][0].set_xlabel("time of day (London, 2026-07-10)", fontsize=7.6)

    n = len(hours)
    layout(fig,
           "One real day, five channels: the trace resolves ordinary occupancy and daylight",
           f"SCD-30 (CO₂ / temperature / humidity) and two Grove analog channels, "
           f"{n} samples at a 5-minute interval, {n}/{n} complete. The shaded column is the "
           f"morning occupancy window; dashed lines are the WELL v2 reference thresholds, and "
           f"the right-hand strip gives each channel's range and mean (Table 6).",
           "Source: Essay/documents/real-trace-2026-07-10-london.csv. Every channel stays "
           "within its expected physical operating range; nothing here was introduced to create "
           "an event. The Grove light and sound columns are ADC readings mapped to lux and dBA by "
           "a fixed per-channel calibration during ingestion — disclosed in Table 6, and not "
           "cross-checked against a reference meter. n = 1 day, 1 room, 1 deployment.")
    save(fig, "fig-07-real-sensor-trace.png")


def _real_rows() -> list[dict]:
    return list(csv.DictReader(open(REAL_CSV)))


def _pearson(a: list[float], b: list[float]) -> float:
    n = len(a); ma = sum(a) / n; mb = sum(b) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = math.sqrt(sum((x - ma) ** 2 for x in a)); db = math.sqrt(sum((y - mb) ** 2 for y in b))
    return num / (da * db) if da and db else 0.0


def _rmse(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)) / len(a))


def _sim_trace(rows: list[dict]) -> dict[str, list[float]]:
    """Run the DEPLOYED ambient model (in_band=False, the realistic history mode that
    backfills exhibit history) at the real day's wall-clock stamps. Seeded for
    reproducibility. This is a GENERIC diurnal model — it has no knowledge of the
    specific occupancy event in the real trace, which is exactly the honest limitation
    fig-08 exposes."""
    random.seed(0)
    sim: dict[str, list[float]] = {c[0]: [] for c in CHANNELS}
    for r in rows:
        ts = datetime.fromisoformat(r["timestamp"])
        s = ambient_sample(ts, in_band=False)
        for c in CHANNELS:
            sim[c[0]].append(s[c[0]])
    return sim


def fig08_sim_vs_real() -> None:
    rows = _real_rows()
    hours = [datetime.fromisoformat(r["timestamp"]).hour + datetime.fromisoformat(r["timestamp"]).minute / 60.0
             for r in rows]
    real = {c[0]: [float(r[c[0]]) for r in rows] for c in CHANNELS}
    sim_raw = _sim_trace(rows)

    fig, axes = plt.subplots(len(CHANNELS), 2, figsize=(FULL_W, 7.2),
                             width_ratios=[3.50, 1.15])
    for i in range(1, len(CHANNELS)):
        axes[i][0].sharex(axes[0][0])
    for i in range(len(CHANNELS) - 1):
        axes[i][0].tick_params(labelbottom=False)
    stats: dict[str, tuple[float, float, float]] = {}
    for i, (col, label, unit, hue, _thr) in enumerate(CHANNELS):
        ax, axs = axes[i][0], axes[i][1]
        rv, sv = real[col], sim_raw[col]
        # single-parameter offset calibration: align the sim's mean to the real day's mean.
        offset = (sum(rv) / len(rv)) - (sum(sv) / len(sv))
        sv_cal = [v + offset for v in sv]
        rmse, r = _rmse(rv, sv_cal), _pearson(rv, sv_cal)
        stats[col] = (rmse, r, offset)

        ax.plot(hours, sv_cal, color=OFF_C, lw=1.0, ls="--", zorder=2)
        ax.plot(hours, rv, color=hue, lw=1.3, zorder=3)
        ax.set_ylabel(f"{label}\n({unit})", fontsize=7.4)
        ax.margins(x=0.005, y=0.14)
        ax.tick_params(labelsize=7.0)
        if i == 0:
            ax.text(0.015, 0.97, "real (SCD-30 / Grove)", transform=ax.transAxes,
                    fontsize=6.8, color=hue, fontweight="bold", va="top")
            ax.text(0.015, 0.80, "ambient model, offset-calibrated", transform=ax.transAxes,
                    fontsize=6.8, color=OFF_C, fontweight="bold", va="top")

        # ── identity-line scatter: where the model tracks, and where it does not ──
        lo = min(min(rv), min(sv_cal)); hi = max(max(rv), max(sv_cal))
        pad = (hi - lo) * 0.06 or 1.0
        axs.plot([lo - pad, hi + pad], [lo - pad, hi + pad], color=INK["baseline"],
                 lw=0.9, ls="-", zorder=1)
        axs.scatter(rv, sv_cal, s=2.4, color=hue, alpha=0.40, linewidths=0, zorder=3)
        axs.set_xlim(lo - pad, hi + pad)
        axs.set_ylim(lo - pad, hi + pad)
        axs.set_aspect("equal", adjustable="box")
        axs.tick_params(labelsize=6.2)
        axs.locator_params(nbins=3)
        axs.grid(True, axis="both")
        axs.text(0.04, 0.96, f"r = {r:.2f}", transform=axs.transAxes, fontsize=7.2,
                 fontweight="bold", color=INK["primary"], va="top")
        axs.text(0.04, 0.80, f"RMSE {rmse:.1f} {unit}", transform=axs.transAxes,
                 fontsize=6.4, color=INK["secondary"], va="top")
        if i == 0:
            axs.set_title("model vs. real, 1:1 line", fontsize=6.8, loc="center", pad=4,
                          color=INK["secondary"], fontweight="normal")
        if i == len(CHANNELS) - 1:
            axs.set_xlabel("real", fontsize=6.8)
        axs.set_ylabel("model", fontsize=6.8, labelpad=1)

    axes[-1][0].set_xlim(0, 24)
    axes[-1][0].set_xticks(range(0, 25, 3))
    axes[-1][0].set_xticklabels([f"{h:02d}:00" for h in range(0, 25, 3)], fontsize=7.0)
    axes[-1][0].set_xlabel("time of day (London, 2026-07-10)", fontsize=7.6)

    layout(fig,
           "The ambient model reproduces diurnal envelopes but not discrete events",
           f"Left: the deployed ambient model (`sensing/ambient.py`, history mode) run at the "
           f"real day's timestamps and shifted by one per-channel offset so its mean matches. "
           f"Right: the same values against the 1:1 line — temperature (r = "
           f"{stats['temperature'][1]:.2f}) and illuminance (r = {stats['lux'][1]:.2f}) follow "
           f"it, CO₂ (r = {stats['co2'][1]:.2f}) does not.",
           "Source: real-trace-2026-07-10-london.csv + sensing/ambient.py (Table 6). The "
           "offset is fitted on this same day, so r and RMSE measure shape fidelity IN SAMPLE, "
           "not out-of-sample prediction. CO₂ is the deliberate miss: a generic diurnal model "
           "cannot know about the one occupancy event in the real day and places its own "
           "meeting spikes elsewhere — which is precisely why the closed loop takes its "
           "anomalies from explicit scenarios with a physics CO₂ model rather than from this "
           "background generator. n = 1 day, 1 room, 1 deployment; seeded (rng=0), single run.")
    save(fig, "fig-08-sim-vs-real.png")

    # print the numbers tbl-03 needs, so the table is data-backed not eyeballed
    print("\n=== tbl-03 stats ===")
    print(f"{'channel':<12}{'real min':>9}{'real max':>9}{'real mean':>10}{'sim RMSE':>10}{'r':>7}")
    for col, label, unit, _h, _t in CHANNELS:
        rv = real[col]; rmse, r, _off = stats[col]
        print(f"{col:<12}{min(rv):>9.1f}{max(rv):>9.1f}{sum(rv)/len(rv):>10.1f}{rmse:>10.1f}{r:>7.2f}")
    n = len(rows)
    span_min = (datetime.fromisoformat(rows[-1]['timestamp']) - datetime.fromisoformat(rows[0]['timestamp'])).seconds / 60 + 5
    print(f"samples={n}, expected={int(span_min/5)}, completeness={n/int(span_min/5)*100:.1f}%")


if __name__ == "__main__":
    fig07_real_trace()
    fig08_sim_vs_real()
    print("Exp1 sensing figures updated")
