"""Generate the REUSE-READY figures from already-collected evidence.

Data sources are real project measurements (DEVLOG P-001/P-023, eval/reports/*.json,
dissertation-evidence-inventory.md). No LLM / API calls here — pure re-plotting.
Run:  env ... .venv/bin/python Essay/documents/figures/src/gen_reuse.py
"""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch, Rectangle

from _style import (FULL_W, INK, OFF_C, ON_C, PALETTE, SEQ_BLUE, STATUS,
                    apply_style, ax_title, despine, layout, save)

apply_style()
REPORTS = Path(__file__).resolve().parents[4] / "eval" / "reports"

# Measured on the deployed Raspberry Pi 4 (8 GB) — DEVLOG P-023 / Table 12.
PI_STAGES = [("rerank (30 candidates)", 187.0), ("embed query", 1.4),
             ("dense search", 0.08), ("BM25 search", 0.01)]
PI_POOL = [(30, 189.0), (5, 24.4)]          # candidate pool → end-to-end latency (s)
PI_FINAL_TOP_K = 5


# ═════════════════════════════════════════════════════════════════════════════
# fig-19 · edge retrieval cost — PROPORTION BAR + log-scale companion
# Form: "99% of the cost" is a share, so the top panel is a single 100%-stacked
# bar where the share is self-evident; the log panel below keeps the three
# sub-second stages readable, which a proportion bar alone cannot do.
# ═════════════════════════════════════════════════════════════════════════════
def fig19_edge_breakdown() -> None:
    names = [n for n, _ in PI_STAGES]
    secs = np.array([v for _, v in PI_STAGES])
    total = secs.sum()
    share = secs / total
    cols = [STATUS["critical"], SEQ_BLUE[4], SEQ_BLUE[3], SEQ_BLUE[2]]

    fig, (axA, axB) = plt.subplots(2, 1, figsize=(FULL_W, 3.55),
                                   height_ratios=[1.0, 1.55])

    # ── A · one retrieval as 100% ────────────────────────────────────────────
    left = 0.0
    for sh, c, nm in zip(share, cols, names):
        axA.barh([0], [sh], left=left, height=0.42, color=c, edgecolor=INK["surface"],
                 linewidth=1.2)
        left += sh
    axA.text(share[0] / 2, 0, f"reranker  {share[0]:.1%}", ha="center", va="center",
             color="white", fontsize=8.6, fontweight="bold")
    axA.annotate(f"everything else {1 - share[0]:.1%}", xy=(1.0, 0.24), xytext=(0.86, 0.72),
                 fontsize=7.2, color=INK["secondary"], ha="center",
                 arrowprops=dict(arrowstyle="-", color=INK["muted"], lw=0.8))
    axA.set_xlim(0, 1.0)
    axA.set_ylim(-0.55, 0.95)
    axA.set_xticks(np.arange(0, 1.01, 0.25), ["0%", "25%", "50%", "75%", "100%"])
    axA.set_yticks([])
    axA.grid(False)
    despine(axA, left=True)
    ax_title(axA, f"A  Share of one retrieval ({total:.1f} s total)")

    # ── B · absolute stage cost, log scale so 0.01 s is still visible ────────
    y = np.arange(len(names))[::-1]
    axB.barh(y, secs, height=0.56, color=cols)
    axB.set_xscale("log")
    axB.set_xlim(0.005, 900)
    axB.set_yticks(y, names, fontsize=7.4)
    axB.set_xlabel("wall-clock latency per retrieval (s, log scale)")
    for yi, v in zip(y, secs):
        axB.text(v * 1.45, yi, f"{v:g} s", va="center", fontsize=7.4,
                 color=INK["primary"], fontweight="bold")
    axB.grid(axis="x")
    axB.grid(axis="y", visible=False)
    axB.margins(y=0.16)
    despine(axB, left=True)
    ax_title(axB, "B  The same four stages in absolute time")

    layout(fig, "On the Pi 4 CPU the reranker is the retrieval budget",
           f"Single instrumented retrieval on the deployed Raspberry Pi 4 (8 GB, Debian 13 "
           f"Lite), candidate pool = 30, {len(names)} pipeline stages. Peak RAM 3.8–4.0 GiB "
           f"with zero swap.",
           "Source: ops/scripts/pi_retrieve_spike.py, DEVLOG P-023 (Table 12). Single measured "
           "run on one device — no repeat trials, so no error bars are drawn; the ~6 s per "
           "candidate is roughly linear in pool size, which is what Figure 18 exploits.")
    save(fig, "fig-19-edge-retrieval-breakdown.png")


# ═════════════════════════════════════════════════════════════════════════════
# fig-20 · candidate pool vs latency — measured points on a linear relation,
# with the degradation boundary drawn in-plot rather than left to the caption.
# ═════════════════════════════════════════════════════════════════════════════
def fig20_candidate_latency() -> None:
    pools = np.array([p for p, _ in PI_POOL], dtype=float)
    lats = np.array([s for _, s in PI_POOL], dtype=float)
    speedup = lats.max() / lats.min()

    fig, ax = plt.subplots(figsize=(FULL_W, 3.30))

    # degradation zone: at pool == FINAL_TOP_K the reranker can no longer select
    ax.axvspan(0, PI_FINAL_TOP_K, color=STATUS["critical"], alpha=0.07, zorder=0)
    ax.axvline(PI_FINAL_TOP_K, color=STATUS["critical"], lw=1.1, ls="--", zorder=2)
    ax.annotate("degradation boundary — at pool = FINAL_TOP_K = 5 the reranker\n"
                "can only rank what it is given, it can no longer select from a pool",
                xy=(PI_FINAL_TOP_K, 132), xytext=(8.4, 208), ha="left", va="top",
                fontsize=6.9, color=STATUS["critical"],
                arrowprops=dict(arrowstyle="-", color=STATUS["critical"], lw=0.8))

    ax.plot(pools, lats, "-", color=ON_C, lw=1.8, zorder=3)
    ax.scatter(pools, lats, s=68, color=ON_C, zorder=4)
    ax.annotate(f"{lats[0]:g} s", (pools[0], lats[0]), textcoords="offset points",
                xytext=(0, 11), ha="center", fontsize=8.6, fontweight="bold", color=ON_C)
    ax.annotate(f"{lats[1]:g} s", (pools[1], lats[1]), textcoords="offset points",
                xytext=(10, 8), ha="left", fontsize=8.6, fontweight="bold", color=ON_C)
    ax.text(pools[0], lats[0] - 14, "pool = 30\n(library default)", fontsize=7.2,
            color=INK["secondary"], va="top", ha="center")
    ax.text(pools[1] + 1.0, lats[1] - 6, "pool = 5\n(chosen operating point)",
            fontsize=7.2, color=INK["secondary"], va="top", ha="left")

    ax.annotate("", xy=(17.5, lats[1] + 5), xytext=(17.5, lats[0] - 5),
                arrowprops=dict(arrowstyle="<|-|>", color=INK["muted"], lw=1.1))
    ax.text(18.3, (lats[0] + lats[1]) / 2, f"{speedup:.1f}× faster", fontsize=8.4,
            fontweight="bold", color=INK["primary"], va="center")

    ax.set_xlim(0, 33)
    ax.set_ylim(-22, 222)
    ax.set_xticks([0, 5, 10, 15, 20, 25, 30])
    ax.set_xlabel("reranker candidate-pool size (chunks scored per query)")
    ax.set_ylabel("end-to-end retrieval latency (s)")
    ax.grid(axis="y")

    layout(fig, "Cutting the candidate pool is the only lever that moved edge latency",
           f"Two measured configurations on the deployed Pi 4; the connecting line is the "
           f"roughly-linear pool-size relation reported in Table 12 (~6 s per candidate at "
           f"default, ~4.9 s/candidate at the tuned point), not interpolated measurements. "
           f"Peak RAM 3.5–4.0 GiB, zero swap, in both.",
           "Source: ops/scripts/pi_retrieve_spike.py, DEVLOG P-023 (Table 12). Two other levers "
           "were tested and did not help: max_length 512→256 (chunks average ~125 tokens, so the "
           "cap was never reached) and extra threads (already saturated at 3.97 of 4 cores). "
           "Single run per configuration, so no error bars; the operating point trades a small, "
           "disclosed precision loss for the speed-up, which is acceptable because the closed "
           "loop fires only occasionally.")
    save(fig, "fig-20-edge-candidate-latency.png")


# ═════════════════════════════════════════════════════════════════════════════
# fig-22 · recall-lift across ablation iterations (development history)
# ═════════════════════════════════════════════════════════════════════════════
def fig22_memory_macrolift() -> None:
    files = [
        ("ablate-memory-20260531T222605Z.json", "iteration 1", "first prompt + schema"),
        ("ablate-memory-20260531T223007Z.json", "iteration 2", "recall block moved into\nthe planner's primary goal"),
        ("ablate-memory-20260531T223417Z.json", "iteration 3", "cause carried verbatim,\nnot paraphrased"),
    ]
    lifts, labels, notes, ns = [], [], [], []
    for fn, lab, note in files:
        d = json.loads((REPORTS / fn).read_text())
        lifts.append(d["macro_lift"]); labels.append(lab); notes.append(note)
        ns.append(len(d["rows"]))

    fig, ax = plt.subplots(figsize=(FULL_W, 3.05))
    x = np.arange(len(lifts))
    ax.axhline(1.0, ls="--", lw=0.9, color=INK["muted"], zorder=1)
    ax.text(-0.38, 1.022, "ceiling — every recurrence case recalled", fontsize=6.9,
            color=INK["muted"], va="bottom", ha="left")
    ax.plot(x, lifts, "-", color=ON_C, lw=1.8, zorder=3)
    ax.scatter(x, lifts, s=76, color=ON_C, zorder=4)
    for xi, v, note in zip(x, lifts, notes):
        ax.annotate(f"{v:.2f}", (xi, v), textcoords="offset points", xytext=(0, 11),
                    ha="center", fontsize=9.0, fontweight="bold", color=ON_C)
        ax.text(xi, -0.155, note, ha="center", va="top", fontsize=6.8,
                color=INK["secondary"])
    ax.set_xticks(x, [f"{l}  (n = {n})" for l, n in zip(labels, ns)], fontsize=7.6)
    ax.tick_params(axis="x", length=0, pad=4)
    ax.set_xlim(-0.45, len(lifts) - 0.55)
    ax.set_ylim(0, 1.20)
    ax.set_yticks(np.arange(0, 1.01, 0.25))
    ax.set_ylabel("macro recall-lift\n(memory ON − memory OFF)")
    ax.grid(axis="y")

    layout(fig, "Recall-lift is a property of the planner prompt, not of retrieval alone",
           f"The same {ns[0]} seeded recurrence tasks and the same episodic store, replayed after "
           f"each change to how the recalled cause is injected into the plan. Retrieval was "
           f"already returning the right episode at iteration 1 — 0.25 measures how often the "
           f"planner then used it.",
           "Source: eval/reports/ablate-memory-20260531T*.json. Development history on an early "
           "n = 4 set across three domains; the final, four-domain n = 12 result is Figure E2. "
           "Single run per iteration, planner temperature 0.")
    save(fig, "fig-22-memory-macrolift.png")


# ═════════════════════════════════════════════════════════════════════════════
# fig-21 · closed-loop replan trajectory (qualitative single case)
# ═════════════════════════════════════════════════════════════════════════════
def fig21_closed_loop() -> None:
    steps = [
        ("Anomaly", ON_C, "monitor\nCO₂ 1220 ppm"),
        ("Plan", SEQ_BLUE[4], "planner"),
        ("Diagnose", SEQ_BLUE[4], "specialist"),
        ("REJECT", STATUS["serious"], "critic"),
        ("Replan #1", STATUS["warning"], "planner"),
        ("MISSED", STATUS["serious"], "verifier"),
        ("Replan #2", STATUS["warning"], "planner"),
        ("MISSED", STATUS["serious"], "verifier"),
        ("FAILED", STATUS["critical"], "incident closed\nhonestly"),
    ]
    fig, ax = plt.subplots(figsize=(FULL_W, 2.05))
    ax.set_axis_off()
    n = len(steps)
    bw, gap = 1.0, 0.34
    for i, (label, col, who) in enumerate(steps):
        x = i * (bw + gap)
        ax.add_patch(FancyBboxPatch((x, 0), bw, 0.72,
                                    boxstyle="round,pad=0,rounding_size=0.07",
                                    facecolor=col, edgecolor="none", zorder=2))
        ax.text(x + bw / 2, 0.36, label, ha="center", va="center", color="white",
                fontsize=6.9, fontweight="bold", zorder=3)
        ax.text(x + bw / 2, -0.12, who, ha="center", va="top", color=INK["secondary"],
                fontsize=6.3)
        if i < n - 1:
            ax.annotate("", xy=(x + bw + gap, 0.36), xytext=(x + bw, 0.36),
                        arrowprops=dict(arrowstyle="-|>", color=INK["muted"], lw=1.1))
    # retry bracket over the two replan cycles
    x3, x8 = 3 * (bw + gap), 7 * (bw + gap) + bw
    ax.plot([x3, x3, x8, x8], [0.86, 0.99, 0.99, 0.86], color=INK["muted"], lw=0.9)
    ax.text((x3 + x8) / 2, 1.05, "replan_count = 2 — the loop retries until its budget is spent",
            ha="center", va="bottom", fontsize=7.0, color=INK["secondary"])
    ax.set_xlim(-0.15, n * (bw + gap) - gap + 0.15)
    ax.set_ylim(-0.62, 1.34)

    layout(fig, "When no available action fixes the anomaly, the loop fails honestly",
           "One real `co2_overcrowded` incident through MainIncidentGraph: the critic rejects the "
           "first diagnosis, two replans are attempted, the verifier finds the target unmet both "
           "times, and the incident is closed FAILED rather than reported as resolved.",
           "Source: DEVLOG P-024 / P-027 and eval/reports/e2e-closed-loop-final-*.json (Table 11). "
           "A single qualitative trajectory, not a rate — all three co2_overcrowded runs in Figure 16 "
           "follow this same path (replan_count = 2 in each).")
    save(fig, "fig-21-closed-loop-replan.png")


# ═════════════════════════════════════════════════════════════════════════════
# fig-14 · plan sharpening: recall OFF vs ON (qualitative)
# ═════════════════════════════════════════════════════════════════════════════
def fig14_plan_sharpening() -> None:
    rows = [
        ("co2-damper", "airquality",
         "Diagnose why CO₂ is at 1300 ppm against the 900 ppm WELL v2 limit …",
         "… explicitly investigating whether the outdoor-air damper is stuck and recirculating "
         "stale air rather than occupant load …"),
        ("thermal-solar", "thermal",
         "Diagnose the cause of the reported 29.0 °C indoor temperature exceeding the "
         "21–25 °C WELL v2 Thermal Comfort T01 …",
         "… explicitly investigating west-facing solar gain and whether blinds or glazing are "
         "failing to reject the afternoon solar load …"),
    ]
    fig = plt.figure(figsize=(FULL_W, 1.40 * len(rows) + 1.20), constrained_layout=False)
    y0, y1 = layout(
        fig, "Recall rewrites a generic diagnostic goal into a cause-specific one",
        "Two real planner outputs for the same anomaly, with episodic recall switched off and on. "
        "The recalled clause is what the specialist then has to confirm or reject — Figure 14 shows "
        "it reaching the diagnosis text, Figure 15 shows the cost when the precedent does not apply.",
        "Source: eval/reports/ablate-memory-20260818T023543Z.json (goals_off / goals_on, verbatim "
        "with ellipses, post the 18 Aug WELL v2 threshold correction). Qualitative illustration of "
        "the mechanism Figure E2 quantifies — two hand-picked cases, not a sample.")

    A_X, A_W = 0.150, 0.385
    B_X, B_W = 0.598, 0.398
    def cw(w, pt):
        return max(12, int((w * FULL_W - 0.12) * 72 / (0.60 * pt) * 0.94))
    n_txt = cw(A_W, 7.0)

    row_h = (y1 - y0) / len(rows)
    for i, (name, dom, off, on) in enumerate(rows):
        ax = fig.add_axes([0.0, y0 + (len(rows) - 1 - i) * row_h, 1.0, row_h])
        ax.set_axis_off(); ax.set_xlim(0, 1); ax.set_ylim(0, 1)
        ax.text(0.012, 0.80, name, fontsize=8.0, fontweight="bold", va="top",
                color=INK["primary"])
        ax.text(0.012, 0.62, dom, fontsize=6.9, va="top", color=INK["secondary"])

        ax.add_patch(FancyBboxPatch((A_X, 0.16), A_W, 0.72,
                                    boxstyle="round,pad=0,rounding_size=0.03",
                                    facecolor=INK["panel"], edgecolor=INK["rule"], lw=0.8))
        ax.text(A_X + 0.016, 0.815, "recall OFF", fontsize=6.6, va="center",
                color=INK["secondary"], fontweight="bold")
        ax.text(A_X + 0.016, 0.695, textwrap.fill(off, n_txt), fontsize=7.0, va="top",
                color=INK["primary"], linespacing=1.42)

        ax.annotate("", xy=(B_X - 0.010, 0.52), xytext=(A_X + A_W + 0.010, 0.52),
                    arrowprops=dict(arrowstyle="-|>", color=ON_C, lw=1.6))
        ax.text((A_X + A_W + B_X) / 2, 0.60, "+recall", ha="center", fontsize=6.0,
                color=ON_C, fontweight="bold")

        ax.add_patch(FancyBboxPatch((B_X, 0.16), B_W, 0.72,
                                    boxstyle="round,pad=0,rounding_size=0.03",
                                    facecolor="#e9f1fc", edgecolor=ON_C, lw=1.0))
        ax.text(B_X + 0.016, 0.815, "recall ON — cause named in the goal", fontsize=6.6,
                va="center", color=ON_C, fontweight="bold")
        ax.text(B_X + 0.016, 0.695, textwrap.fill(on, cw(B_W, 7.0)), fontsize=7.0,
                va="top", color=INK["primary"], linespacing=1.42)

    save(fig, "fig-14-plan-sharpening-example.png")


if __name__ == "__main__":
    fig19_edge_breakdown()
    fig20_candidate_latency()
    fig22_memory_macrolift()
    fig21_closed_loop()
    fig14_plan_sharpening()
    print("reuse figures written to Essay/documents/figures/")
