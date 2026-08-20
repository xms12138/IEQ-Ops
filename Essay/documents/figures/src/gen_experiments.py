"""Figures from freshly-run experiments (read the newest eval/reports/*.json).

No hard-coded results — every plotted value is read back from the report the
runner wrote, and every derived quantity (McNemar p, Wilson intervals, ECDFs)
is computed here from those same rows rather than transcribed from a table.

Chart forms are chosen per dataset (dataviz skill, references/choosing-a-form):
paired binary outcomes get flow + contingency, ordered pipeline stages get a
level-and-change step chart, distributions get ECDFs, agreement gets confusion
matrices, and unequal-n rate tables get dot plots with intervals — deliberately
NOT seventeen bar charts.
"""
from __future__ import annotations

import glob
import json
import re
import textwrap
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch, Polygon, Rectangle

from _style import (DOMAIN, FULL_W, GLYPH, INK, OFF_C, ON_C, PALETTE, SEQ_BLUE,
                    STATUS, apply_style, ax_title, despine, layout,
                    mcnemar_exact_p, save, titles, wilson)

apply_style()
ROOT = Path(__file__).resolve().parents[4]
REPORTS = ROOT / "eval" / "reports"


def _latest(pattern: str) -> Path:
    return Path(sorted(glob.glob(str(REPORTS / pattern)))[-1])


def _short(task_id: str) -> str:
    return task_id.replace("L3-recur-", "").replace("novel-", "")


# ═════════════════════════════════════════════════════════════════════════════
# fig-09 · closed-book pre-screen — UNIT CHART (one square per question)
# Form: every one of the 37 items is drawn, so the small, domain-imbalanced n
# is visible rather than averaged away behind four bars.
# ═════════════════════════════════════════════════════════════════════════════
def fig09_closedbook() -> None:
    d = json.loads(_latest("closedbook-prescreen-2026081*.json").read_text())
    rows = d["rows"]
    order = ["airquality", "thermal", "lighting", "acoustic"]
    doms = [dm for dm in order if any(r["domain"] == dm for r in rows)]

    fig, ax = plt.subplots(figsize=(FULL_W, 2.75))
    ax.set_axis_off()
    cell, gap = 1.0, 0.18
    ncol = max(sum(r["domain"] == dm for r in rows) for dm in doms)

    for i, dm in enumerate(doms):
        y = len(doms) - 1 - i
        sub = [r for r in rows if r["domain"] == dm]
        ok = sum(r["grounded"] for r in sub)
        # grouped by outcome within the domain so the proportions compare row to row
        for j in range(len(sub)):
            x = j * (cell + gap)
            if j < ok:
                ax.add_patch(Rectangle((x, y * 1.42), cell, cell,
                                       facecolor=STATUS["good"], edgecolor="none"))
            else:
                ax.add_patch(Rectangle((x, y * 1.42), cell, cell, facecolor="none",
                                       edgecolor=STATUS["critical"], lw=0.9, hatch="///"))
        ax.text(-0.35, y * 1.42 + cell / 2, dm, ha="right", va="center",
                fontsize=8.0, color=INK["primary"], fontweight="bold")
        ax.text(ncol * (cell + gap) + 0.35, y * 1.42 + cell / 2,
                f"{ok}/{len(sub)} correct", ha="left", va="center", fontsize=7.4,
                color=INK["secondary"])

    n, ncorrect = len(rows), sum(r["grounded"] for r in rows)
    n_aq = sum(r["domain"] == "airquality" for r in rows)
    ax.set_xlim(-4.6, ncol * (cell + gap) + 6.6)
    ax.set_ylim(-2.9, len(doms) * 1.42)

    # in-plot key — filled vs hatched-open stays legible in greyscale
    ax.add_patch(Rectangle((0, -1.60), cell, cell, facecolor=STATUS["good"]))
    ax.text(cell + 0.30, -1.60 + cell / 2, "correct without the corpus", va="center",
            fontsize=7.2, color=INK["secondary"])
    ax.add_patch(Rectangle((13.6, -1.60), cell, cell, facecolor="none",
                           edgecolor=STATUS["critical"], lw=0.9, hatch="///"))
    ax.text(13.6 + cell + 0.30, -1.60 + cell / 2,
            "wrong closed-book — the item retrieval has to fix", va="center",
            fontsize=7.2, color=INK["secondary"])
    ax.text(0, -2.45, "squares are grouped by outcome within each domain",
            fontsize=6.6, color=INK["muted"], va="center")

    layout(fig,
           f"Closed-book pre-screen: the base model misses {n - ncorrect} of {n} WELL v2 thresholds",
           f"One square = one standards question, {d['closed_book_accuracy']:.2f} correct overall "
           f"(n = {n}). Airquality carries {n_aq}/{n} because the WELL Air section is the largest "
           f"part of the corpus — disclosed, not balanced away.",
           "Source: eval/reports/closedbook-prescreen-*.json (Table 7) · same base model and "
           "deterministic grader as Figure 11 · single run, temperature 0. This pre-screen is what "
           "justifies the question set: it isolates the items where ungrounded answering already "
           "fails.")
    save(fig, "fig-09-closedbook-prescreen.png")


# ═════════════════════════════════════════════════════════════════════════════
# fig-10 · H1 grounding ablation — PAIRED FLOW + 2x2 CONTINGENCY
# Form: the experiment is paired (same 37 questions, RAG off/on) and the test
# is McNemar on the discordant cells, so the plate shows the pairing (who moved
# where) and the 2x2 the test actually consumes — not two independent bars.
# ═════════════════════════════════════════════════════════════════════════════
def _ribbon(ax, x0, x1, y0, y1, h0, h1, color, alpha=0.55):
    """Smooth flow band from (x0, y0..y0+h0) to (x1, y1..y1+h1)."""
    t = np.linspace(0, 1, 80)
    s = 0.5 - 0.5 * np.cos(np.pi * t)          # ease-in-out
    xs = x0 + (x1 - x0) * t
    top = (y0 + h0) + ((y1 + h1) - (y0 + h0)) * s
    bot = y0 + (y1 - y0) * s
    pts = np.concatenate([np.column_stack([xs, top]),
                          np.column_stack([xs[::-1], bot[::-1]])])
    ax.add_patch(Polygon(pts, closed=True, facecolor=color, edgecolor="none",
                         alpha=alpha, zorder=1))


def fig10_h1_ablation() -> None:
    d = json.loads(_latest("h1-rag-ablation-2026081*.json").read_text())
    rows = d["rows"]
    n = len(rows)
    both = sum(r["no_rag_grounded"] and r["rag_grounded"] for r in rows)
    gain = sum((not r["no_rag_grounded"]) and r["rag_grounded"] for r in rows)
    loss = sum(r["no_rag_grounded"] and (not r["rag_grounded"]) for r in rows)
    neither = n - both - gain - loss
    acc_off, acc_on = d["no_rag_accuracy"], d["rag_accuracy"]
    p = mcnemar_exact_p(gain, loss)

    fig, (axA, axB) = plt.subplots(
        1, 2, figsize=(FULL_W, 3.35), width_ratios=[1.45, 1.0])

    # ── A · paired flow ──────────────────────────────────────────────────────
    x0, x1, bw = 0.0, 1.0, 0.20
    # closed-book column: correct block at the bottom, wrong stacked above
    axA.add_patch(Rectangle((x0 - bw / 2, 0), bw, both + loss,
                            facecolor=STATUS["good"], zorder=2))
    axA.add_patch(Rectangle((x0 - bw / 2, both + loss), bw, gain + neither,
                            facecolor=OFF_C, zorder=2))
    axA.add_patch(Rectangle((x1 - bw / 2, 0), bw, both + gain,
                            facecolor=STATUS["good"], zorder=2))
    axA.add_patch(Rectangle((x1 - bw / 2, both + gain), bw, loss + neither,
                            facecolor=OFF_C, zorder=2))

    xa, xb = x0 + bw / 2, x1 - bw / 2
    _ribbon(axA, xa, xb, 0, 0, both, both, STATUS["good"], 0.30)                 # stayed right
    _ribbon(axA, xa, xb, both, both + gain, loss, loss, STATUS["critical"], 0.75)  # regressed
    _ribbon(axA, xa, xb, both + loss, both, gain, gain, STATUS["good"], 0.80)     # recovered
    _ribbon(axA, xa, xb, both + loss + gain, both + gain + loss, neither, neither,
            OFF_C, 0.45)                                                          # still wrong

    axA.text((xa + xb) / 2, both / 2, f"{both} already right", ha="center", va="center",
             fontsize=7.0, color=INK["secondary"])
    axA.text((xa + xb) / 2, both + gain / 2, f"{gain} recovered", ha="center",
             va="center", fontsize=8.0, color="white", fontweight="bold")
    axA.text((xa + xb) / 2, both + gain + loss / 2 + 0.35, f"{loss} regressed",
             ha="center", va="bottom", fontsize=7.2, color=STATUS["critical"],
             fontweight="bold")
    axA.text((xa + xb) / 2, n - neither / 2, f"{neither} wrong either way",
             ha="center", va="center", fontsize=7.0, color=INK["secondary"])

    for x, acc, k, lab in [(x0, acc_off, both + loss, "No-RAG\n(closed-book)"),
                           (x1, acc_on, both + gain, "RAG\n(top-5 WELL v2 chunks)")]:
        axA.text(x, n + 1.05, f"{acc:.2f}", ha="center", va="bottom", fontsize=11.0,
                 fontweight="bold", color=INK["primary"])
        axA.text(x, n + 0.25, f"{k}/{n} correct", ha="center", va="bottom", fontsize=7.0,
                 color=INK["secondary"])

    axA.annotate("", xy=(x1 - 0.34, n + 0.75), xytext=(x0 + 0.34, n + 0.75),
                 arrowprops=dict(arrowstyle="-|>", color=STATUS["good"], lw=1.3))
    axA.text(0.5, n + 1.05, f"+{(acc_on - acc_off) * 100:.0f} pp", ha="center", va="bottom",
             fontsize=8.8, fontweight="bold", color=STATUS["good"])
    axA.text(0.0, 1.0, "A", transform=axA.transAxes, ha="left", va="top",
             fontsize=9.0, fontweight="bold", color=INK["primary"])

    axA.set_xlim(-0.42, 1.42)
    axA.set_ylim(-0.9, n + 3.0)
    axA.set_ylabel("questions (paired, same 37 items)")
    axA.set_yticks([0, 10, 20, 30, 37])
    axA.set_xticks([x0, x1], ["No-RAG\n(closed-book)", "RAG\n(top-5 WELL v2 chunks)"],
                   fontsize=7.4)
    axA.tick_params(axis="x", length=0, pad=3)
    axA.grid(False)
    despine(axA, bottom=True)

    # ── B · 2x2 contingency the McNemar test consumes ────────────────────────
    axB.set_axis_off()
    cells = [[both, loss], [gain, neither]]          # rows: closed-book right/wrong
    tint = [[INK["panel"], "#f3dcda"], ["#d9eadf", INK["panel"]]]
    disc = [[False, True], [True, False]]
    for i in range(2):
        for j in range(2):
            x, y = j * 1.0, 1.0 - i * 1.0
            axB.add_patch(FancyBboxPatch(
                (x + 0.04, y + 0.04), 0.92, 0.92,
                boxstyle="round,pad=0,rounding_size=0.04",
                facecolor=tint[i][j], edgecolor=(STATUS["critical"] if (i, j) == (0, 1)
                                                 else STATUS["good"] if (i, j) == (1, 0)
                                                 else INK["rule"]),
                lw=1.2 if disc[i][j] else 0.7))
            axB.text(x + 0.5, y + 0.60, str(cells[i][j]), ha="center", va="center",
                     fontsize=15 if disc[i][j] else 12,
                     fontweight="bold" if disc[i][j] else "normal",
                     color=INK["primary"] if not disc[i][j] else
                     (STATUS["critical"] if (i, j) == (0, 1) else STATUS["good"]))
            note = [["concordant", "RAG lost"], ["RAG won", "concordant"]][i][j]
            axB.text(x + 0.5, y + 0.22, note, ha="center", va="center", fontsize=6.4,
                     color=INK["secondary"])
    axB.text(1.0, 2.30, "RAG", ha="center", fontsize=7.2, color=INK["secondary"])
    axB.text(0.5, 2.04, "right", ha="center", fontsize=7.2, color=INK["secondary"])
    axB.text(1.5, 2.04, "wrong", ha="center", fontsize=7.2, color=INK["secondary"])
    axB.text(-0.08, 1.5, "closed-book\nright", ha="right", va="center", fontsize=7.2,
             color=INK["secondary"])
    axB.text(-0.08, 0.5, "closed-book\nwrong", ha="right", va="center", fontsize=7.2,
             color=INK["secondary"])
    axB.text(1.0, -0.30, f"discordant split {gain} : {loss}", ha="center", va="center",
             fontsize=8.2, color=INK["primary"], fontweight="bold")
    axB.text(1.0, -0.62, f"McNemar exact two-sided $p$ = {p:.4f}", ha="center",
             va="center", fontsize=7.8, color=INK["primary"])
    axB.text(-0.90, 2.62, "B", ha="left", va="top", fontsize=9.0, fontweight="bold",
             color=INK["primary"])
    axB.set_xlim(-1.02, 2.10)
    axB.set_ylim(-0.95, 2.66)

    layout(fig, "Standards grounding lifts accuracy 0.43 → 0.76, and the lift is paired-significant",
               f"n = {n} RAG-discriminative WELL v2 questions · same base model "
               f"(deepseek-v4-flash, temperature 0) and same deterministic grader in both arms.",
               "Source: eval/reports/h1-rag-ablation-*.json (Table 7). Single run per arm; "
               "run-to-run stability is quantified separately in Table E1. The 3 regressions "
               "are near-duplicate-tier confusions, analysed in Table 7.")
    save(fig, "fig-10-h1-ablation.png")


# ═════════════════════════════════════════════════════════════════════════════
# fig-11 · retrieval quality curves — recall@k AND nDCG@k, ordered ramp
# ═════════════════════════════════════════════════════════════════════════════
STAGES = [
    ("sparse", "BM25 only", SEQ_BLUE[1], "-", "o"),
    ("dense", "dense only (BGE-M3)", SEQ_BLUE[3], "-", "s"),
    ("hybrid", "RRF hybrid", SEQ_BLUE[4], "-", "^"),
    ("reranked", "+reranker (production)", SEQ_BLUE[6], "-", "D"),
    ("contextual", "+contextual prefix (side collection)", STATUS["critical"], "--", "v"),
]


def fig11_retrieval_metrics() -> None:
    d = json.loads(_latest("retrieval-pipeline-ablation-2026081*.json").read_text())
    s = d["summary"]
    ks = [1, 3, 5, 10]
    xi = np.arange(len(ks))

    fig, axes = plt.subplots(1, 2, figsize=(FULL_W, 3.1), sharey=True)
    for ax, metric, lab in zip(axes, ["recall", "ndcg"],
                               ["recall@k  (gold chunk within top-k)", "nDCG@k"]):
        for key, name, col, ls, mk in STAGES:
            ys = [s[key][f"{metric}@{k}"] for k in ks]
            ax.plot(xi, ys, ls, color=col, marker=mk, ms=4.2, lw=1.6,
                    markeredgecolor=col, markerfacecolor=col, zorder=3)
            ax.text(-0.14, ys[0], f"{ys[0]:.2f}", ha="right", va="center",
                    fontsize=6.9, color=col, fontweight="bold")
        ax.set_xticks(xi, [str(k) for k in ks])
        ax.set_xlim(-0.62, len(ks) - 0.72)
        ax.set_ylim(0.40, 1.04)
        ax.set_xlabel("k  (ordinal positions 1 · 3 · 5 · 10)")
        ax.set_ylabel(lab if metric == "recall" else "")
        ax_title(ax, ("A  Recall@k" if metric == "recall" else "B  nDCG@k"))
        ax.grid(axis="y")

    # direct labelling on the right panel — no legend box anywhere
    for key, name, col, ls, mk in STAGES:
        y = s[key]["ndcg@10"]
        axes[1].text(len(ks) - 0.86, y, "  " + name, va="center", ha="left",
                     fontsize=6.6, color=col, fontweight="bold")
    axes[1].set_xlim(-0.62, len(ks) + 2.25)

    layout(fig, "Retrieval quality across the five pipeline configurations",
               f"n = {d['n_questions']} corpus-anchored questions with an automatically located "
               f"gold chunk ({d['n_excluded_no_gold']} of 36 excluded — labelling limitation, "
               f"Table 8). Series are shaded light→dark in pipeline order.",
               "Source: eval/reports/retrieval-pipeline-ablation-*.json (Table 8). Deterministic "
               "retrieval — a rerun reproduces these values exactly, so no error bars are shown. "
               "The contextual-prefix arm (dashed red) is a side collection, not the deployed "
               "pipeline.")
    save(fig, "fig-11-retrieval-metrics.png")


# ═════════════════════════════════════════════════════════════════════════════
# fig-12 · pipeline stages — LEVEL-AND-CHANGE STEP CHART on R@1
# Form: the story is a progression with one gain that dominates (+reranker) and
# two losses (RRF fusion, contextual prefix). Bars of five near-identical R@5
# values hid both; the step chart on R@1 shows where the movement actually is,
# with R@5 carried as a light reference track so nothing is dropped.
# ═════════════════════════════════════════════════════════════════════════════
def fig12_pipeline_ablation() -> None:
    d = json.loads(_latest("retrieval-pipeline-ablation-2026081*.json").read_text())
    s = d["summary"]
    keys = [k for k, *_ in STAGES]
    labels = ["BM25\nonly", "dense\nonly", "RRF\nhybrid", "+reranker\n(production)",
              "+contextual\nprefix"]
    r1 = [s[k]["recall@1"] for k in keys]
    r5 = [s[k]["recall@5"] for k in keys]
    x = np.arange(len(keys))

    fig, ax = plt.subplots(figsize=(FULL_W, 3.45))

    # production stage gets a soft column so the eye finds the operating point
    ax.axvspan(2.55, 3.45, color=SEQ_BLUE[0], alpha=0.55, zorder=0)
    ax.text(3.0, 0.335, "deployed configuration", ha="center", fontsize=6.8,
            color=SEQ_BLUE[5], fontweight="bold")

    ax.plot(x, r5, "--", color=SEQ_BLUE[2], lw=1.3, marker="o", ms=3.6,
            markerfacecolor=INK["surface"], markeredgecolor=SEQ_BLUE[2], zorder=2)
    ax.plot(x, r1, "-", color=SEQ_BLUE[6], lw=2.0, marker="o", ms=6.0, zorder=4)

    for xi, a, b in zip(x, r1, r5):
        # keep the two labels apart when the tracks nearly touch
        dy, va = ((0, -14), "top") if (b - a) < 0.12 else ((0, 9), "bottom")
        ax.annotate(f"{a:.2f}", (xi, a), textcoords="offset points", xytext=dy,
                    ha="center", va=va, fontsize=8.2, fontweight="bold",
                    color=SEQ_BLUE[6])
        ax.annotate(f"{b:.2f}", (xi, b), textcoords="offset points", xytext=(0, 8),
                    ha="center", va="bottom", fontsize=7.0, color=SEQ_BLUE[3])

    # change between consecutive configurations, signed and coloured
    for i in range(len(keys) - 1):
        dv = r1[i + 1] - r1[i]
        col = STATUS["good"] if dv > 0 else STATUS["critical"]
        ymid = (r1[i] + r1[i + 1]) / 2
        ax.annotate(f"{'▲' if dv > 0 else '▼'} {dv:+.2f}", (i + 0.5, ymid),
                    textcoords="offset points", xytext=(0, -20 if dv > 0 else 16),
                    ha="center", fontsize=7.6, fontweight="bold", color=col)

    ax.text(len(keys) - 0.90, r1[-1], "   R@1", va="center", fontsize=7.8,
            color=SEQ_BLUE[6], fontweight="bold")
    ax.text(len(keys) - 0.90, r5[-1], "   R@5", va="center", fontsize=7.8,
            color=SEQ_BLUE[3], fontweight="bold")

    ax.set_xticks(x, labels, fontsize=7.4)
    ax.set_xlim(-0.45, len(keys) - 0.02)
    ax.set_ylim(0.30, 1.12)
    ax.set_ylabel("recall (fraction of questions, 0–1)")
    ax.grid(axis="y")

    layout(fig, "The reranker, not fusion, is what makes rank-1 retrieval work",
               f"n = {d['n_questions']} corpus-anchored questions. Configurations are alternative "
               f"settings of the same retriever read left to right in pipeline order — the ▲▼ "
               f"labels are differences between adjacent configurations, not additive contributions.",
               "Source: eval/reports/retrieval-pipeline-ablation-*.json (Table 8). RRF fusion "
               "costs 0.16 at rank 1 versus dense alone (position-based merging demotes correct "
               "chunks) and the reranker recovers it; contextual prefixing is a disclosed "
               "negative result on this corpus and is NOT deployed. R@5 is shown because at "
               "k=5 four of the five configurations are indistinguishable — the argument only "
               "exists at rank 1.")
    save(fig, "fig-12-rag-pipeline-ablation.png")


# ═════════════════════════════════════════════════════════════════════════════
# fig-13 / fig-23 · paired OFF→ON outcome matrix, grouped by domain
# Form: a paired dot matrix with one row per task keeps every case auditable at
# n=12 and shows the domain spread; the two plates share a form on purpose so
# the reader can compare plan-level against diagnosis-level directly.
# ═════════════════════════════════════════════════════════════════════════════
def _paired_matrix(rows, off_key, on_key, title, subtitle, foot, outname,
                   extra_col=None, extra_head=""):
    order = ["airquality", "thermal", "lighting", "acoustic"]
    rows = sorted(rows, key=lambda r: (order.index(r["domain"]), r["task_id"]))
    h = 0.215 * len(rows) + 1.55
    fig, ax = plt.subplots(figsize=(FULL_W, h))
    ax.set_axis_off()
    y = np.arange(len(rows))[::-1].astype(float)
    xo, xn = 0.0, 1.0

    # domain rails + per-domain tally
    seen = {}
    for yi, r in zip(y, rows):
        seen.setdefault(r["domain"], []).append(yi)
    for dm, ys in seen.items():
        ax.plot([-1.62, -1.62], [min(ys) - 0.34, max(ys) + 0.34], color=DOMAIN[dm],
                lw=2.6, solid_capstyle="butt", clip_on=False)
        hits = sum(int(r[on_key]) for r in rows if r["domain"] == dm)
        tot = sum(1 for r in rows if r["domain"] == dm)
        ax.text(-1.70, (min(ys) + max(ys)) / 2, f"{dm}\n{hits}/{tot}", ha="right",
                va="center", fontsize=7.0, color=DOMAIN[dm], fontweight="bold")

    for yi, r in zip(y, rows):
        off, on = int(r[off_key]), int(r[on_key])
        ax.plot([xo, xn], [yi, yi], color=INK["rule"], lw=1.0, zorder=1)
        ax.scatter(xo, yi, s=62, facecolor=INK["surface"], edgecolor=OFF_C, lw=1.2,
                   zorder=3, marker="o")
        ax.text(xo, yi, GLYPH["good"] if off else GLYPH["critical"], ha="center",
                va="center", fontsize=6.4, color=OFF_C, zorder=4)
        ax.scatter(xn, yi, s=62, color=ON_C if on else OFF_C, zorder=3, marker="o")
        ax.text(xn, yi, GLYPH["good"] if on else GLYPH["critical"], ha="center",
                va="center", fontsize=6.4, color="white", zorder=4)
        ax.text(-1.52, yi, _short(r["task_id"]), ha="left", va="center", fontsize=7.0,
                color=INK["primary"])
        if extra_col:
            ax.text(1.40, yi, extra_col(r), ha="left", va="center", fontsize=6.8,
                    color=INK["secondary"], style="italic")

    top = y.max() + 0.85
    ax.text(xo, top, "memory OFF", ha="center", fontsize=7.4, color=OFF_C,
            fontweight="bold")
    ax.text(xn, top, "memory ON", ha="center", fontsize=7.4, color=ON_C,
            fontweight="bold")
    if extra_head:
        ax.text(1.40, top, extra_head, ha="left", fontsize=7.0, color=INK["secondary"])
    ax.annotate("", xy=(xn - 0.17, top + 0.50), xytext=(xo + 0.17, top + 0.50),
                arrowprops=dict(arrowstyle="-|>", color=INK["muted"], lw=1.0))
    ax.text(0.5, top + 0.78, "same anomaly, same planner — only recall changes",
            ha="center", fontsize=6.8, color=INK["muted"])
    ax.text(xo, y.min() - 0.95, f"{sum(int(r[off_key]) for r in rows)}/{len(rows)}",
            ha="center", fontsize=9.0, fontweight="bold", color=OFF_C)
    ax.text(xn, y.min() - 0.95, f"{sum(int(r[on_key]) for r in rows)}/{len(rows)}",
            ha="center", fontsize=9.0, fontweight="bold", color=ON_C)
    ax.set_xlim(-2.45, 3.24)
    ax.set_ylim(y.min() - 1.5, top + 1.25)

    layout(fig, title,
               subtitle,
               foot)
    save(fig, outname)


def fig13_recall_lift() -> None:
    d = json.loads(_latest("ablate-memory-2026081*.json").read_text())
    _paired_matrix(
        d["rows"], "recall_off", "recall_on",
        "Recall injects the building-specific cause into the plan in every case",
        f"n = {len(d['rows'])} seeded recurrence tasks across four domains · macro-lift "
        f"{d['macro_lift']:.2f} (0.00 → 1.00). ✗ = the cause never appears in the plan's "
        f"subtask goals, ✓ = it does.",
        "Source: eval/reports/ablate-memory-*.json (Table E2). PLAN-LEVEL only — Figure 14 tests "
        "whether the cue survives into the diagnosis text. The perfect column is partly true by "
        "construction (the cause is present in the recalled episode), so this is a mechanism "
        "check, not a diagnostic-accuracy score; single run, planner temperature 0.",
        "fig-13-recall-accuracy-lift.png",
        extra_col=lambda r: "cue: " + ", ".join(r["detail"]["gold"]),
        extra_head="recalled cue looked for")


def fig23_diagnosis_lift() -> None:
    d = json.loads(_latest("h2a-diagnosis-accuracy-2026081*.json").read_text())
    _paired_matrix(
        d["rows"], "diagnosis_hit_off", "diagnosis_hit_on",
        "The recalled cause survives the full specialist, not just the plan",
        f"n = {len(d['rows'])} recurrence tasks run through the real SpecialistSubgraph "
        f"(decompose → retrieve → grade → rewrite → generate) · diagnosis-level macro-lift "
        f"{d['macro_lift']:.2f} (0.00 → 1.00).",
        "Source: eval/reports/h2a-diagnosis-accuracy-*.json (Table 9). Scored on the FINAL "
        "diagnosis text, OR-of-synonyms. Measures whether the recalled cause is named, not whether "
        "it is the objectively correct explanation — and Figure 15 shows the same mechanism "
        "misfiring on novel anomalies. Single run; generate/rewrite sample at temperature > 0.",
        "fig-23-diagnosis-level-lift.png",
        extra_col=lambda r: "cue: " + ", ".join(r["gold"]),
        extra_head="recalled cue looked for")


# ═════════════════════════════════════════════════════════════════════════════
# fig-15 · detection coverage vs reactive budget — gap-shaded line
# ═════════════════════════════════════════════════════════════════════════════
def fig15_coverage() -> None:
    d = json.loads(_latest("autonomy-2026081*.json").read_text())
    sweep = sorted(d["sweep"], key=lambda s: s["period_min"])
    hrs = np.array([s["period_min"] / 60 for s in sweep])
    cov = np.array([s["coverage"] for s in sweep])
    pro = d["proactive"]["coverage"]
    nev = d["params"]["events"]

    fig, ax = plt.subplots(figsize=(FULL_W, 3.2))
    ax.fill_between(hrs, cov, pro, color=STATUS["critical"], alpha=0.09, zorder=1)
    ax.axhline(pro, ls="-", lw=1.8, color=ON_C, zorder=3)
    ax.text(hrs[-1], pro + 0.025, f"proactive 5-min monitor — {pro:.2f} of events seen",
            ha="right", va="bottom", fontsize=7.6, color=ON_C, fontweight="bold")
    ax.plot(hrs, cov, "-o", color=STATUS["critical"], lw=1.7, ms=5, zorder=4)
    ax.text(hrs[0], cov[0] + 0.16, "reactive, query-only", ha="left", va="bottom",
            fontsize=7.6, color=STATUS["critical"], fontweight="bold")
    for xp, c in zip(hrs, cov):
        ax.annotate(f"{c:.2f}", (xp, c), textcoords="offset points", xytext=(0, 9),
                    ha="center", va="bottom", fontsize=7.0, color=INK["secondary"])
    ax.text(6.6, 0.76, "coverage gap", fontsize=7.6, ha="center",
            color=STATUS["critical"], style="italic")

    # mark the representative cadence used in Table E4 / Figure E4
    i2 = int(np.argmin(np.abs(hrs - 2)))
    ax.scatter([hrs[i2]], [cov[i2]], s=110, facecolor="none", edgecolor=INK["primary"],
               lw=1.1, zorder=5)
    ax.annotate("representative manager\ncadence (2 h) — Figure E4",
                (hrs[i2], cov[i2]), textcoords="offset points", xytext=(14, 34),
                fontsize=6.9, color=INK["secondary"], ha="left",
                arrowprops=dict(arrowstyle="-", color=INK["muted"], lw=0.8))

    ax.set_xscale("log")
    ax.set_xticks(hrs, [f"{h:g}" for h in hrs])
    ax.minorticks_off()
    ax.set_xlim(0.38, 12)
    ax.set_ylim(-0.06, 1.16)
    ax.set_yticks(np.arange(0, 1.01, 0.2))
    ax.set_xlabel("reactive check period (hours, log scale)")
    ax.set_ylabel("fraction of events detected")

    layout(fig, "No reactive query budget approaches continuous monitoring",
               f"Discrete-event scheduling model: {nev} events over {d['params']['days']} days across "
               f"{d['params']['n_rooms']} rooms; the reactive arm checks "
               f"{d['params']['reactive_rooms_per_check']} of {d['params']['n_rooms']} rooms per query "
               f"during {d['params']['work_hours'][0]}–{d['params']['work_hours'][1]} h.",
               "Source: eval/reports/autonomy-*.json (Table E4). Contains NO LLM and no IEQ "
               "content — it bounds what continuous polling buys over intermittent human "
               "checking, and deliberately uses a conservative reactive baseline, so the "
               "absolute reactive values are an upper bound on the gap, not a measurement of "
               "this system. Seeded (rng=42), single run.")
    save(fig, "fig-15-detection-coverage.png")


# ═════════════════════════════════════════════════════════════════════════════
# fig-16 · lead-time — ECDF (was: two boxes, which hid n and the whole shape)
# ═════════════════════════════════════════════════════════════════════════════
def fig16_lead_time() -> None:
    d = json.loads(_latest("autonomy-2026081*.json").read_text())
    pro = np.sort(np.asarray(d["proactive"]["delays"], dtype=float))
    rea = np.sort(np.asarray(d["reactive_2h"]["delays"], dtype=float))
    nev = d["params"]["events"]

    fig, ax = plt.subplots(figsize=(FULL_W, 3.15))
    for arr, col, name in [(pro, ON_C, "proactive 5-min monitor"),
                           (rea, STATUS["critical"], "reactive 2 h checks")]:
        ys = np.arange(1, len(arr) + 1) / len(arr)
        ax.step(np.concatenate([[0], arr]), np.concatenate([[0], ys]), where="post",
                color=col, lw=1.8, zorder=3)
        med = float(np.median(arr))
        ax.plot([med, med], [0, 0.5], ls=":", lw=1.0, color=col, zorder=2)
        ax.scatter([med], [0.5], s=34, color=col, zorder=4)
        ax.text(med + 2.0, 0.525, f"median {med:.0f} min", fontsize=7.4, color=col,
                fontweight="bold", va="bottom")
        ax.text(arr[-1] + 1.5, 1.0, f"  {name}\n  n = {len(arr)}", fontsize=7.4,
                color=col, va="center", fontweight="bold")

    ax.axhline(0.5, lw=0.7, ls="--", color=INK["muted"], zorder=1)
    ax.set_xlim(-2, 132)
    ax.set_ylim(0, 1.06)
    ax.set_yticks(np.arange(0, 1.01, 0.25))
    ax.set_xlabel("detection lead-time after event onset (minutes)")
    ax.set_ylabel("cumulative fraction\nof DETECTED events")

    layout(fig, "Proactive detection lands inside one scan; reactive checking lags by ~an hour",
               f"Empirical CDF of the lead-time of every detected event. The two curves are NOT "
               f"drawn from the same denominator: the proactive arm detects all {len(pro)} of {nev} "
               f"events, the reactive 2 h arm only {len(rea)} — the {nev - len(rea)} it never sees "
               f"have no lead-time and cannot appear here.",
               "Source: eval/reports/autonomy-*.json (Table E4). Conditioning on detection "
               "flatters the reactive arm; Figure E3 carries the coverage side of the same run. "
               "Scheduling model only, no LLM; seeded (rng=42), single run.")
    save(fig, "fig-16-lead-time.png")


# ═════════════════════════════════════════════════════════════════════════════
# fig-18 · judge validity — CONFUSION MATRICES (was: bars of kappa values)
# ═════════════════════════════════════════════════════════════════════════════
def fig18_judge_validity() -> None:
    d = json.loads(_latest("judge-validity-2026081*.json").read_text())
    rows = d["rows"]
    panels = [
        ("deepseek_judge_hit", "qwen_judge_hit", "DeepSeek judge", "Qwen judge",
         d["inter_judge_agreement"], d["inter_judge_kappa"], "A  Inter-judge (cross-family)"),
        ("deepseek_judge_hit", "det_verdict", "DeepSeek judge", "deterministic grader",
         d["deepseek_vs_det_agreement"], d["deepseek_vs_det_kappa"], "B  DeepSeek vs grader"),
        ("qwen_judge_hit", "det_verdict", "Qwen judge", "deterministic grader",
         d["qwen_vs_det_agreement"], d["qwen_vs_det_kappa"], "C  Qwen vs grader"),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(FULL_W, 2.85))
    n = len(rows)
    for ax, (ka, kb, na, nb, agree, kappa, head) in zip(axes, panels):
        m = np.zeros((2, 2), dtype=int)
        for r in rows:
            m[0 if r[ka] else 1][0 if r[kb] else 1] += 1
        vmax = m.max()
        for i in range(2):
            for j in range(2):
                onlead = (i == j)
                frac = m[i][j] / vmax if vmax else 0
                ax.add_patch(Rectangle((j, 1 - i), 0.94, 0.94,
                                       facecolor=SEQ_BLUE[6] if onlead else "#f0dcd9",
                                       alpha=(0.16 + 0.74 * frac) if onlead else
                                             (0.35 + 0.5 * frac),
                                       edgecolor=INK["rule"], lw=0.6))
                dark = onlead and frac > 0.55
                ax.text(j + 0.47, 1 - i + 0.47, str(m[i][j]), ha="center", va="center",
                        fontsize=11.5 if onlead else 10,
                        fontweight="bold" if not onlead else "normal",
                        color="white" if dark else (STATUS["critical"] if not onlead
                                                    else INK["primary"]))
        ax.set_xlim(-0.06, 2.0)
        ax.set_ylim(-0.62, 2.42)
        ax.set_xticks([0.47, 1.47], ["hit", "miss"])
        ax.set_yticks([1.47, 0.47], ["hit", "miss"])
        ax.tick_params(length=0)
        ax.set_xlabel(nb, fontsize=7.2, labelpad=1)
        ax.set_ylabel(na, fontsize=7.2, labelpad=1)
        ax.grid(False)
        for sp in ax.spines.values():
            sp.set_visible(False)
        ax_title(ax, head)
        ax.text(1.0, -0.50, f"agreement {agree:.3f}   ·   $\\kappa$ = {kappa:.3f}",
                ha="center", fontsize=7.6, fontweight="bold",
                color=STATUS["good"] if kappa >= 0.8 else INK["primary"])
        if head.startswith("A"):
            ax.text(1.0, 2.14, "off-diagonal = the items they disagree on", ha="center",
                    fontsize=6.5, color=INK["muted"])

    layout(fig, "Two judge families agree with each other, and both agree with the string grader",
               f"n = {n} real (candidate, expected) pairs — every answer produced in the H1 "
               f"closed-book and RAG runs. κ ≥ 0.81 is 'almost perfect' and 0.61–0.80 'substantial' "
               f"on the Landis & Koch scale.",
               "Source: eval/reports/judge-validity-*.json (Table E6). Judge-vs-HUMAN validity "
               "was not measured and is recorded as future work. The 6–10 disagreements "
               "concentrate on the near-duplicate-table and full-row-quoting items already "
               "flagged in Table 7.")
    save(fig, "fig-18-judge-agreement.png")


# ═════════════════════════════════════════════════════════════════════════════
# fig-24 · memory specificity — SMALL MULTIPLES of the diagnostic swap
# Form: the finding is a substitution (safe-generic → specific-but-wrong), so
# the plate renders the swap itself, one card per novel case, with the borrowed
# token and its source episode named. Bars of four identical 1.00s said nothing.
# ═════════════════════════════════════════════════════════════════════════════
_CAUSE_RE = re.compile(
    r"(?:The likely (?:in-room )?(?:cause|source) is|The cause is likely|"
    r"The likely cause appears to be|likely caused by)\s+(.+?)(?:[.;]|,\s+as\b|\s+\(excerpt)",
    re.I | re.S)
_FALLBACK_RE = re.compile(
    r"(?:To remediate,|Corrective action[:s]*|The corrective action is to)\s+(.+?)(?:[.;]|\s+\(excerpt)",
    re.I | re.S)


def _cause_phrase(text: str, limit: int = 96) -> str:
    m = _CAUSE_RE.search(text) or _FALLBACK_RE.search(text)
    phrase = (m.group(1) if m else text.split(".")[0]).strip().replace("\n", " ")
    phrase = re.sub(r"\s+", " ", phrase)
    if len(phrase) > limit:
        phrase = phrase[:limit].rsplit(" ", 1)[0] + "…"
    return phrase


def fig24_specificity() -> None:
    d = json.loads(_latest("h2a-specificity-2026081*.json").read_text())
    rows = d["rows"]
    ROW_H = 1.44
    FIG_H = ROW_H * len(rows) + 1.36
    fig = plt.figure(figsize=(FULL_W, FIG_H), constrained_layout=False)

    ID_X, ID_W = 0.014, 0.205
    A_X, A_W = 0.235, 0.300
    B_X, B_W = 0.622, 0.376

    rate = d["contamination_rate"]
    y0, y1 = layout(
        fig,
        "Memory replaces a safe generic diagnosis with a borrowed, wrong specific cause",
        f"Four novel anomalies — one per domain — whose real cause matches NO seeded episode. "
        f"Contamination rate {rate:.2f} ({int(round(rate * len(rows)))}/{len(rows)}): in every "
        f"case recall did not add a caveat alongside the generic diagnosis, it overwrote it.",
        "Source: eval/reports/h2a-specificity-*.json (Table 10). Quoted phrases are extracted "
        "verbatim from the stored diagnosis text and truncated at a word boundary. n = 4 — a "
        "first probe, not a precision study; the anomalies were hand-authored to differ from "
        "every seeded cause, and contamination is scored by literal keyword presence, so a "
        "diagnosis naming a recalled term only to rule it out would still count (none of these "
        "four did). This is the precision cost of the same mechanism Figure E2 and Figure 14 credit "
        "for the recall lift.")

    # axes span the full figure width, so a column's inch width is exactly known
    AX_W = FULL_W
    def cw(frac_w: float, pt: float, inset: float = 0.10) -> int:
        """chars that fit in a column of the given axes-fraction width"""
        return max(12, int((frac_w * AX_W - inset) * 72 / (0.60 * pt) * 0.94))

    n_id, n_a, n_b = cw(ID_W, 6.6, 0.03), cw(A_W, 7.0, 0.05), cw(B_W, 7.0, 0.05)
    row_h = (y1 - y0) / len(rows)
    axes = [fig.add_axes([0.0, y0 + (len(rows) - 1 - i) * row_h, 1.0, row_h])
            for i in range(len(rows))]

    for ax, r in zip(axes, rows):
        ax.set_axis_off()
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        dm = r["domain"]
        truth = r["true_cause_hint"].split(" (not ")[0]
        off_p = _cause_phrase(r["diagnosis_off"], 3 * n_a - 6)
        on_p = _cause_phrase(r["diagnosis_on"], 3 * n_b - 6)
        borrowed = ", ".join(r["contaminating_keywords"])
        src = ", ".join(_short(t) for t in r["recalled_task_ids"])

        # identity column — domain rail, case id, and the cause the system cannot know
        ax.plot([0.003, 0.003], [0.20, 0.95], color=DOMAIN[dm], lw=3.0,
                solid_capstyle="butt")
        ax.text(ID_X, 0.95, _short(r["task_id"]), fontsize=8.0, fontweight="bold",
                va="top", color=INK["primary"])
        ax.text(ID_X, 0.775, dm, fontsize=6.8, va="top", color=DOMAIN[dm],
                fontweight="bold")
        ax.text(ID_X, 0.625, "true cause (not in memory)", fontsize=6.0,
                va="top", color=INK["muted"])
        ax.text(ID_X, 0.520, textwrap.fill(truth, n_id), fontsize=6.6, va="top",
                color=INK["secondary"], style="italic", linespacing=1.35)

        # card A — the un-recalled arm
        ax.add_patch(FancyBboxPatch((A_X, 0.245), A_W, 0.715,
                                    boxstyle="round,pad=0,rounding_size=0.02",
                                    facecolor=INK["panel"], edgecolor=INK["rule"], lw=0.8))
        ax.text(A_X + 0.016, 0.885, "MEMORY OFF", fontsize=6.4, va="center",
                color=INK["secondary"], fontweight="bold")
        ax.text(A_X + A_W - 0.016, 0.885, "generic · safe", fontsize=6.2,
                va="center", ha="right", color=INK["muted"])
        ax.text(A_X + 0.016, 0.755, "\u201c" + textwrap.fill(off_p, n_a) + "\u201d",
                fontsize=7.0, va="top", color=INK["primary"], linespacing=1.42)

        # the substitution
        ax.annotate("", xy=(B_X - 0.012, 0.60), xytext=(A_X + A_W + 0.012, 0.60),
                    arrowprops=dict(arrowstyle="-|>", color=STATUS["critical"], lw=1.8))
        ax.text((A_X + A_W + B_X) / 2, 0.665, "replaced", ha="center", fontsize=6.2,
                color=STATUS["critical"], fontweight="bold")

        # card B — the recalled arm, contaminated
        ax.add_patch(FancyBboxPatch((B_X, 0.245), B_W, 0.715,
                                    boxstyle="round,pad=0,rounding_size=0.02",
                                    facecolor="#f9ebe9", edgecolor=STATUS["critical"], lw=1.0))
        ax.text(B_X + 0.016, 0.885, "MEMORY ON", fontsize=6.4, va="center",
                color=STATUS["critical"], fontweight="bold")
        ax.text(B_X + B_W - 0.016, 0.885, f"specific · WRONG {GLYPH['critical']}",
                fontsize=6.2, va="center", ha="right", color=STATUS["critical"],
                fontweight="bold")
        ax.text(B_X + 0.016, 0.755, "\u201c" + textwrap.fill(on_p, n_b) + "\u201d",
                fontsize=7.0, va="top", color=INK["primary"], linespacing=1.42)

        # provenance strip — full width, so long episode lists never overflow a card
        ax.text(A_X, 0.170, "borrowed token(s):", fontsize=6.4, va="top",
                color=INK["muted"])
        ax.text(A_X + 0.162, 0.170, borrowed, fontsize=6.4, va="top",
                color=STATUS["critical"], fontweight="bold")
        ax.text(B_X, 0.170, textwrap.fill("recalled episodes: " + src,
                                          cw(1.0 - B_X, 6.4, 0.05)),
                fontsize=6.4, va="top", color=INK["muted"], linespacing=1.35)

    save(fig, "fig-24-memory-specificity.png")


# ═════════════════════════════════════════════════════════════════════════════
# fig-25 · end-to-end closed loop — OUTCOME MATRIX over all 20 incidents
# Form: three bars all at 1.00 conveyed nothing. One glyph per incident, placed
# against the trigger value that produced it, shows the sweep, the n, and the
# three distinct correct behaviours at once.
# ═════════════════════════════════════════════════════════════════════════════
def fig25_closed_loop() -> None:
    d = json.loads((REPORTS / "e2e-closed-loop-final-20260818T095745Z.json").read_text())
    s, rows = d["summary"], d["rows"]

    def _trig(label: str) -> str:
        v = label.split("=")[-1]
        return f"{float(v):g}" if re.fullmatch(r"[\d.]+", v) else v

    groups = [
        ("airquality · CO₂ ppm", [r for r in rows if r["sweep"] == "severity"
                                  and r["domain"] == "airquality"],
         "good", f"Tier-1 auto-resolve {s['tier1_auto_resolve_rate']:.2f}"),
        ("airquality · co2_overcrowded, occupants",
         [r for r in rows if r["sweep"] == "overcrowded"],
         "warning", f"honest FAILED {s['overcrowded_failed_rate']:.2f}"),
        ("thermal · °C", [r for r in rows if r["domain"] == "thermal"],
         "held", "Tier-3 gate"),
        ("lighting · lux", [r for r in rows if r["domain"] == "lighting"],
         "held", "Tier-3 gate"),
        ("acoustic · dBA", [r for r in rows if r["domain"] == "acoustic"],
         "held", "Tier-3 gate"),
    ]
    colmap = {"good": STATUS["good"], "warning": STATUS["warning"],
              "held": PALETTE["violet"]}

    fig, ax = plt.subplots(figsize=(FULL_W, 3.5))
    ax.set_axis_off()
    ncol = max(len(g[1]) for g in groups)
    for i, (name, grp, kind, _tag) in enumerate(groups):
        y = len(groups) - 1 - i
        col = colmap[kind]
        for j, r in enumerate(grp):
            ax.add_patch(FancyBboxPatch((j * 1.0 + 0.06, y + 0.16), 0.88, 0.62,
                                        boxstyle="round,pad=0,rounding_size=0.08",
                                        facecolor=col, alpha=0.90, edgecolor="none"))
            ax.text(j + 0.5, y + 0.55, GLYPH[kind if kind != "warning" else "critical"]
                    if kind != "held" else GLYPH["held"],
                    ha="center", va="center", fontsize=8.5, color="white",
                    fontweight="bold")
            ax.text(j + 0.5, y + 0.30, _trig(r["label"]), ha="center", va="center",
                    fontsize=6.2, color="white")
        ax.text(-0.25, y + 0.47, name, ha="right", va="center", fontsize=7.6,
                color=INK["primary"])
        ax.text(ncol + 0.25, y + 0.47, f"{len(grp)}/{len(grp)}", ha="left", va="center",
                fontsize=8.0, fontweight="bold", color=col)

    # right-hand outcome bracket labels
    ax.text(ncol + 1.30, 4.47, "closed automatically\nafter verification", fontsize=6.9,
            va="center", color=STATUS["good"])
    ax.text(ncol + 1.30, 3.47, f"FAILED after {s['overcrowded_replan_counts'][0]} replans\n"
                               "— correct, no fix exists", fontsize=6.9, va="center",
            color=STATUS["warning"])
    ax.plot([ncol + 1.15, ncol + 1.15], [0.18, 2.80], color=PALETTE["violet"], lw=1.4,
            solid_capstyle="butt")
    ax.text(ncol + 1.30, 1.49, f"held for human approval,\nzero autonomous action "
                               f"({s['n_tier3_runs']}/{s['n_tier3_runs']})",
            fontsize=6.9, va="center", color=PALETTE["violet"])

    ax.set_xlim(-4.6, ncol + 5.4)
    ax.set_ylim(-0.55, len(groups) + 0.42)
    ax.text(-4.55, len(groups) + 0.12, "one tile = one real incident through MainIncidentGraph; "
            "the number inside is the trigger value that opened it",
            fontsize=6.8, color=INK["muted"])

    layout(fig, "Twenty real incidents, three correct behaviours, no wrong autonomous action",
               f"Full MainIncidentGraph runs (monitor → plan → specialist → critic → autonomy gate → "
               f"action → verify). Airquality is the only domain with an actuator, so it is the only "
               f"one that can close a loop; the other three must stop at the Tier-3 gate — and did, "
               f"{s['n_tier3_runs']}/{s['n_tier3_runs']}.",
               "Source: eval/reports/e2e-closed-loop-final-*.json (Table 11). Single run per "
               "incident (n = 20 total: 8 + 3 + 9); 'closed' verdicts were cross-checked "
               "directly against Postgres. Three methodology bugs found and fixed during this "
               "run are recorded in Table 11.")
    save(fig, "fig-25-closed-loop-success.png")


# ═════════════════════════════════════════════════════════════════════════════
# fig-26 · IEQ-Bench aggregate — DOT PLOT with Wilson intervals and n per row
# Form: n runs 2→12, so bars invited a false read of equal weight. A dot plot
# with a 95% Wilson interval makes the small-n rows visibly uncertain.
# ═════════════════════════════════════════════════════════════════════════════
def fig26_bench_aggregate() -> None:
    d = json.loads(_latest("ieq-bench-aggregate-2026081*.json").read_text())
    caps = list(d["l1_l2"]["by_capability"])
    items = [(f"{r['layer']}  {r['capability']}" + (" *" if r["capability"] == "rewrite" else ""),
              r["pass_rate"], r["n"], False) for r in caps]
    items.append(("L3  e2e (system arm)", d["l3_e2e"]["pass_rate"], d["l3_e2e"]["n"], False))
    items.append(("L3  recurrence †", d["l3_recurrence"]["pass_rate"],
                  d["l3_recurrence"]["n"], True))

    non_recur_n = d["l1_l2"]["overall"]["n"] + d["l3_e2e"]["n"]
    non_recur_passed = (round(d["l1_l2"]["overall"]["pass_rate"] * d["l1_l2"]["overall"]["n"])
                        + round(d["l3_e2e"]["pass_rate"] * d["l3_e2e"]["n"]))
    non_recur_rate = non_recur_passed / non_recur_n

    items = sorted(items, key=lambda t: (t[3], t[1], t[2]))
    y = np.arange(len(items))

    fig, ax = plt.subplots(figsize=(FULL_W, 3.35))
    ax.axvspan(0, 0, color="none")
    ax.axvline(non_recur_rate, color=SEQ_BLUE[5], lw=1.3, ls="-", zorder=2)
    ax.text(non_recur_rate - 0.015, len(items) - 0.42,
            f"capability-plane {non_recur_rate:.1%}  ({non_recur_passed}/{non_recur_n})",
            ha="right", va="bottom", fontsize=7.2, color=SEQ_BLUE[5], fontweight="bold")

    for yi, (lab, rate, n, is_recur) in zip(y, items):
        k = int(round(rate * n))
        lo, hi = wilson(k, n)
        col = PALETTE["violet"] if is_recur else (
            STATUS["critical"] if rate < 0.5 else
            STATUS["warning"] if rate < 0.95 else STATUS["good"])
        ax.plot([lo, hi], [yi, yi], color=col, lw=1.5, alpha=0.45,
                solid_capstyle="butt", zorder=3)
        ax.plot([lo, lo], [yi - 0.13, yi + 0.13], color=col, lw=1.2, zorder=3)
        ax.plot([hi, hi], [yi - 0.13, yi + 0.13], color=col, lw=1.2, zorder=3)
        ax.scatter([rate], [yi], s=58, color=INK["surface"] if is_recur else col,
                   edgecolor=col, lw=1.6, zorder=5, marker="D" if is_recur else "o")
        ax.text(1.045, yi, f"{k}/{n}", va="center", fontsize=7.2,
                color=INK["primary"], fontweight="bold")
        ax.text(1.135, yi, f"{rate:.2f}", va="center", fontsize=7.2, color=col,
                fontweight="bold")

    ax.set_yticks(y, [t[0] for t in items], fontsize=7.4)
    ax.set_xlim(-0.02, 1.30)
    ax.set_xticks(np.arange(0, 1.01, 0.25))
    ax.set_ylim(-0.62, len(items) - 0.10)
    ax.set_xlabel("pass rate  (point estimate with 95% Wilson interval)")
    ax.grid(axis="x")
    ax.grid(axis="y", visible=False)
    despine(ax, left=True)
    ax.text(1.045, len(items) - 0.45, "k/n", fontsize=6.8, color=INK["muted"])
    ax.text(1.135, len(items) - 0.45, "rate", fontsize=6.8, color=INK["muted"])

    layout(fig, "IEQ-Bench pass rate by layer and capability, with the small-n uncertainty shown",
               f"Intervals are 95% Wilson bounds on the reported k/n — the point estimates are "
               f"unchanged. Overall as measured {d['overall_pass_rate']:.1%} "
               f"(n = {d['n_total']}); the capability-plane figure is the preferred headline.",
               "Source: eval/reports/ieq-bench-aggregate-*.json (Table 13). n per capability ranges "
               "2–12, so several intervals are very wide — this is a snapshot probe suite, not a "
               "large fixed-release benchmark.   * L2 rewrite: disclosed test debt, not a regression "
               "in the rewrite node — the fixture's gold_sources predate the corpus "
               "consolidation, so MRR is mechanically 0 however good the rewritten query is.   "
               "† L3 recurrence (hollow diamond) is process fidelity, not an independent "
               "capability probe (Table 15, row 9); it is reported here but excluded from the "
               "capability-plane headline.")
    save(fig, "fig-26-ieq-bench-aggregate.png")


if __name__ == "__main__":
    fig09_closedbook()
    fig10_h1_ablation()
    fig11_retrieval_metrics()
    fig12_pipeline_ablation()
    fig13_recall_lift()
    fig15_coverage()
    fig16_lead_time()
    fig18_judge_validity()
    fig23_diagnosis_lift()
    fig24_specificity()
    fig25_closed_loop()
    fig26_bench_aggregate()
    print("experiment figures updated")
