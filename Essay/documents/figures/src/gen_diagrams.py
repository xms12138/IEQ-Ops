"""Schematic diagrams (no data / no API) — problem framing, architecture, pipelines.
Consistent with the shared palette so they read as one system with the data figures.
Two of these (fig02, fig05) use a typed-edge grammar (solid = control flow, dashed =
persistence I/O, dotted = MCP tool call) instead of the plain box-arrow chain used for
the linear pipelines (fig01, fig04), so the set is not visually monotone.
"""
from __future__ import annotations

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

from _style import INK, PALETTE, STATUS, apply_style, save

apply_style()


def box(ax, x, y, w, h, text, fc, tc="white", fs=10, weight="bold"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.06",
                                facecolor=fc, edgecolor="none"))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", color=tc,
            fontsize=fs, fontweight=weight, wrap=True)


def container(ax, x, y, w, h, label, ec, fs=8.2):
    """Light outlined wrapper for a subgraph's real node chain (not a filled box)."""
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08",
                                facecolor="none", edgecolor=ec, lw=1.4, linestyle=(0, (4, 2))))
    ax.text(x + 0.12, y + h - 0.1, label, ha="left", va="top", fontsize=fs,
            fontweight="bold", color=ec)


def arrow(ax, x1, y1, x2, y2, color=None, style="solid", lw=1.6, rad=0.0, label=None,
          label_fs=7.2, label_color=None):
    a = FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=15,
                        color=color or INK["muted"], lw=lw, linestyle=style,
                        connectionstyle=f"arc3,rad={rad}" if rad else None,
                        shrinkA=0, shrinkB=0)
    ax.add_patch(a)
    if label:
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2 + (0.45 if rad else 0.0)
        ax.text(mx, my, label, ha="center", va="center", fontsize=label_fs,
                color=label_color or INK["secondary"], style="italic",
                bbox=dict(facecolor=INK["surface"], edgecolor="none", pad=0.6))


def blank(figsize):
    fig, ax = plt.subplots(figsize=figsize)
    ax.axis("off")
    ax.set_xlim(0, 10); ax.set_ylim(0, 10)
    return fig, ax


# ── fig-01 · problem chain → solution, framed by Sense·Deploy·Communicate ────
def fig01_problem_sdc():
    fig, ax = blank((11, 4.6))
    probs = ["Invisible IEQ\nrisks\n(CO₂ → cognition)", "Dashboard\noverload,\nreactive FM",
             "Generic LLM\nhallucinates\non standards", "Assistants are\npassive +\nstateless"]
    for i, p in enumerate(probs):
        box(ax, 0.3 + i * 2.45, 6.6, 2.1, 2.4, p, PALETTE["blue"], fs=9)
        if i < 3:
            arrow(ax, 0.3 + i * 2.45 + 2.1, 7.8, 0.3 + (i + 1) * 2.45, 7.8)
        # every problem box feeds the solution, not just the one a single arrow would sit under
        box_cx = 0.3 + i * 2.45 + 2.1 / 2
        arrow(ax, box_cx, 6.5, 5.1, 5.32, lw=1.0, color=INK["muted"])
    box(ax, 0.7, 3.3, 8.8, 1.9,
        "IEQ-Ops: grounded (RAG) · memory-augmented · autonomous multi-agent operator",
        PALETTE["violet"], fs=10)
    for i, (lab, col) in enumerate([("SENSE", STATUS["good"]), ("DEPLOY", PALETTE["aqua"]),
                                    ("COMMUNICATE", PALETTE["orange"])]):
        box(ax, 0.6 + i * 3.2, 0.7, 2.9, 1.5, lab, col, fs=11)
        arrow(ax, 1.9 + i * 3.2, 3.2, 2.05 + i * 3.2, 2.25)
    ax.set_title("Problem chain → solution, framed by Sense · Deploy · Communicate",
                 fontsize=12.5, fontweight="bold")
    save(fig, "fig-01-problem-sdc.png")


# ── fig-04 · sensing pipeline (with the ingest-time bounds filter) ──────────
def fig04_sensing():
    fig, ax = blank((11.6, 2.6))
    stages = [("SCD-30 + Grove\nlight / sound", PALETTE["green"]),
              ("Arduino MKR\nWiFi 1010", PALETTE["blue"]),
              ("MQTT →\nMosquitto", PALETTE["aqua"]),
              ("Bounds filter\n(reject 0 / 12,509 ppm\n→ null, not substituted)", STATUS["warning"]),
              ("Postgres\n(time-series)", PALETTE["violet"]),
              ("Monitor\n(5-min scan)", STATUS["serious"])]
    w = 1.68
    for i, (s, c) in enumerate(stages):
        x = 0.25 + i * 1.92
        fs = 7.6 if i == 3 else 9
        box(ax, x, 3.4, w, 3.2, s, c, fs=fs)
        if i < len(stages) - 1:
            arrow(ax, x + w, 5.0, x + 1.92, 5.0)
    ax.set_xlim(0, 11.6)
    ax.set_ylim(2.9, 7.1)
    ax.set_title("Sensing pipeline: sensor node → MQTT → bounds filter → Postgres → Monitor",
                 fontsize=11.5, fontweight="bold")
    save(fig, "fig-04-sensing-pipeline.png")


# ── fig-05 · Agentic RAG: 5-node subgraph loop, retrieve node expanded ───────
def fig05_rag():
    fig, ax = blank((11.4, 6.6))
    ax.set_xlim(-0.2, 11.4); ax.set_ylim(0.6, 9.6)

    # top row — the SpecialistSubgraph loop
    node_y, node_h = 7.3, 1.3
    decompose = (0.2, node_y, 1.7, node_h)
    retrieve = (2.15, node_y, 1.7, node_h)
    grade = (4.1, node_y, 1.7, node_h)
    generate = (8.5, node_y, 1.9, node_h)
    rewrite = (4.1, 5.15, 1.7, node_h)

    box(ax, *decompose, "decompose", PALETTE["violet"], fs=9)
    box(ax, *retrieve, "retrieve", INK["secondary"], fs=9)
    box(ax, *grade, "grade ★", PALETTE["orange"], fs=9)
    box(ax, *generate, "generate ★", PALETTE["orange"], fs=9)
    box(ax, *rewrite, "rewrite", PALETTE["blue"], fs=9)

    cy = node_y + node_h / 2
    arrow(ax, decompose[0] + decompose[2], cy, retrieve[0], cy)
    arrow(ax, retrieve[0] + retrieve[2], cy, grade[0], cy)
    arrow(ax, grade[0] + grade[2], cy, generate[0], cy, label="sufficient", label_fs=7.5)
    arrow(ax, grade[0] + 0.5, node_y, rewrite[0] + 0.5, 5.15 + node_h,
          label="insufficient", label_fs=7.5, color=STATUS["warning"])
    arrow(ax, rewrite[0], 5.15 + node_h / 2, retrieve[0] + 0.3, node_y,
          rad=0.35, color=STATUS["warning"], label="retry, capped ×3", label_fs=7.2)

    ax.text(5.9, 6.55, "no LLM", fontsize=7, color=INK["muted"], ha="center", style="italic")
    ax.text(0.2, 8.85, "SpecialistSubgraph — one compiled instance, shared by all four domains",
            fontsize=10.5, fontweight="bold", color=INK["primary"], ha="left")

    # nested inset — what "retrieve" actually does (deterministic, no LLM)
    inset_x0, inset_y0, inset_w, inset_h = 1.9, 1.0, 9.3, 3.3
    ax.add_patch(FancyBboxPatch((inset_x0, inset_y0), inset_w, inset_h,
                                boxstyle="round,pad=0.03,rounding_size=0.08",
                                facecolor=INK["panel"], edgecolor=INK["rule"], lw=1.0))
    ax.text(inset_x0 + 0.15, inset_y0 + inset_h - 0.18, "retrieve, expanded — mcp-rag-server (deterministic, no LLM)",
            fontsize=8.3, color=INK["secondary"], fontweight="bold", va="top")

    iy = inset_y0 + 0.35
    ih = 1.1
    q = (2.15, iy, 1.4, ih)
    bm25 = (4.0, iy + 0.75, 1.7, ih * 0.85)
    dense = (4.0, iy - 0.35, 1.7, ih * 0.85)
    rrf = (6.1, iy, 1.5, ih)
    rerank = (8.0, iy, 1.9, ih)
    box(ax, *q, "sub-query", INK["secondary"], fs=8)
    box(ax, *bm25, "BM25\n(sparse)", PALETTE["yellow"], fs=7.6, tc=INK["primary"])
    box(ax, *dense, "BGE-M3\n(dense)", PALETTE["blue"], fs=7.6)
    box(ax, *rrf, "RRF\nfusion", PALETTE["aqua"], fs=7.6)
    box(ax, *rerank, "bge-reranker\n-v2-m3", PALETTE["violet"], fs=7.6)

    arrow(ax, q[0] + q[2], iy + ih * 0.9, bm25[0], bm25[1] + bm25[3] * 0.5, lw=1.3)
    arrow(ax, q[0] + q[2], iy + ih * 0.1, dense[0], dense[1] + dense[3] * 0.5, lw=1.3)
    arrow(ax, bm25[0] + bm25[2], bm25[1] + bm25[3] * 0.5, rrf[0], rrf[1] + rrf[3] * 0.7, lw=1.3)
    arrow(ax, dense[0] + dense[2], dense[1] + dense[3] * 0.5, rrf[0], rrf[1] + rrf[3] * 0.3, lw=1.3)
    arrow(ax, rrf[0] + rrf[2], rrf[1] + rrf[3] * 0.5, rerank[0], rerank[1] + rerank[3] * 0.5, lw=1.3)
    ax.text(inset_x0 + inset_w - 0.1, iy + ih * 0.5, "top-k\nchunks", fontsize=7.6,
            ha="right", va="center", color=INK["primary"], fontweight="bold")
    arrow(ax, rerank[0] + rerank[2], rerank[1] + rerank[3] * 0.5, inset_x0 + inset_w - 0.75,
          iy + ih * 0.5, lw=1.3)

    # link the top-row "retrieve" node down into the inset
    arrow(ax, retrieve[0] + retrieve[2] / 2, node_y, q[0] + q[2] / 2, inset_y0 + inset_h,
          style="dashed", color=INK["muted"], lw=1.2)

    ax.set_title("Agentic RAG: the 5-node subgraph loop, with the retrieve node expanded",
                 fontsize=12, fontweight="bold")
    save(fig, "fig-05-rag-pipeline.png")


# ── fig-02 · system architecture (3 graphs + subgraph), typed edges ─────────
def fig02_arch():
    fig, ax = blank((12.6, 9.4))
    ax.set_xlim(-0.5, 13.2); ax.set_ylim(-1.0, 11.7)

    # ── MainIncidentGraph: a real node chain, not a text block ───────────────
    main = (0.1, 8.9, 12.4, 1.5)
    node_names = ["monitor", "memory", "planner", "dispatch", "specialist",
                  "critic", "gate", "action", "verify"]
    node_w, node_h, node_gap = 1.2, 0.85, 0.135
    node_y = main[1] + 0.28
    node_x = [0.25 + i * (node_w + node_gap) for i in range(len(node_names))]
    container(ax, *main, "MainIncidentGraph — fires every 5 min", PALETTE["blue"])
    for i, name in enumerate(node_names):
        box(ax, node_x[i], node_y, node_w, node_h, name, PALETTE["blue"], fs=7.6)
        if i < len(node_names) - 1:
            arrow(ax, node_x[i] + node_w, node_y + node_h / 2,
                  node_x[i + 1], node_y + node_h / 2, lw=1.3)

    def node_cx(i):
        return node_x[i] + node_w / 2

    # replan loop-back arcs entirely ABOVE the container, clear of every box
    loop_y = main[1] + main[3] + 0.12
    arrow(ax, node_cx(8), loop_y, node_cx(2), loop_y, rad=0.32,
          color=STATUS["critical"], lw=1.4)
    ax.text(node_cx(5), loop_y + 0.95, "replan on verifier miss (capped → FAILED)",
            ha="center", va="bottom", fontsize=7.2, color=STATUS["critical"], style="italic")
    ax.text((node_x[7] + node_w + node_x[8]) / 2, node_y - 0.16, "15-min suspend",
            ha="center", va="top", fontsize=5.8, color=INK["secondary"], style="italic")

    # ── SpecialistSubgraph: nested container with its own real node chain ───
    spec = (3.6, 6.55, 6.0, 1.55)
    container(ax, *spec, "SpecialistSubgraph — one shared instance, all 4 domains", PALETTE["violet"])
    spec_names = ["decompose", "retrieve", "grade", "rewrite", "generate"]
    sw, sh, sgap = 1.02, 0.75, 0.135
    sx = [spec[0] + 0.18 + i * (sw + sgap) for i in range(len(spec_names))]
    sy = spec[1] + 0.28
    for i, name in enumerate(spec_names):
        box(ax, sx[i], sy, sw, sh, name, PALETTE["violet"], fs=6.6)
        if i < len(spec_names) - 1:
            arrow(ax, sx[i] + sw, sy + sh / 2, sx[i + 1], sy + sh / 2, lw=1.1)
    arrow(ax, sx[2] + sw * 0.3, sy, sx[1] + sw * 0.7, sy, rad=-0.55,
          color=PALETTE["orange"], lw=1.0, style="dashed")

    # control flow: specialist node invokes the subgraph — long enough that
    # the label sits beside visible line, not on top of it
    arrow(ax, node_cx(4), node_y, node_cx(4), spec[1] + spec[3], lw=1.4)
    ax.text(node_cx(4) + 0.25, (node_y + spec[1] + spec[3]) / 2, "invoke(subtask)",
            ha="left", va="center", fontsize=7, color=INK["secondary"], style="italic",
            bbox=dict(facecolor=INK["surface"], edgecolor="none", pad=0.5))

    # ── ReflectionGraph / ConversationalGraph — outer x-ranges, leaving a
    # clear central corridor (≈4.7–8.3) for the Specialist→MCP line below ──
    refl = (0.1, 4.6, 4.6, 1.4)
    conv = (8.3, 4.6, 4.3, 1.4)
    box(ax, *refl, "ReflectionGraph (weekly)\nepisodic → semantic + procedural",
        PALETTE["aqua"], fs=8.6)
    box(ax, *conv, "ConversationalGraph (on-demand)\nmemory-first Q&A + voice",
        PALETTE["orange"], fs=8.6)

    # ── Postgres / Qdrant — same outer-left / outer-right placement ─────────
    pg = (0.6, 2.3, 3.4, 1.3)
    qd = (8.9, 2.3, 3.4, 1.3)
    box(ax, *pg, "Postgres\n(incidents, checkpoints)", PALETTE["green"], fs=8.4)
    box(ax, *qd, "Qdrant\n(episodic, semantic, standards)", PALETTE["green"], fs=8.4)

    # ── MCP servers — centred, directly below the Specialist subgraph ───────
    mcp = (3.6, 0.1, 6.0, 1.2)
    box(ax, *mcp, "MCP servers: sensor · actuator · rag · ticket", INK["secondary"], fs=9)

    # persistence I/O (dashed): Main <-> stores, routed along the outer
    # margins (outside x=0.1..12.4) so the curve never enters the
    # Reflection/Conversational or Specialist footprints
    arrow(ax, main[0] + 0.3, main[1], pg[0] + 0.25, pg[1] + pg[3],
          style="dashed", color=STATUS["good"], rad=-0.5, lw=1.3)
    arrow(ax, main[0] + main[2] - 0.3, main[1], qd[0] + qd[2] - 0.25, qd[1] + qd[3],
          style="dashed", color=STATUS["good"], rad=0.5, lw=1.3)

    # ReflectionGraph / ConversationalGraph -> stores (short, directly below)
    arrow(ax, refl[0] + 1.6, refl[1], pg[0] + pg[2] * 0.6, pg[1] + pg[3],
          style="dashed", color=STATUS["good"])
    arrow(ax, conv[0] + 1.3, conv[1], qd[0] + qd[2] * 0.4, qd[1] + qd[3],
          style="dashed", color=STATUS["good"])

    # MCP tool calls (dotted): Specialist subgraph is directly above MCP —
    # a clean vertical drop through the central corridor, no crossing
    arrow(ax, (spec[0] + spec[2] / 2) - 0.4, spec[1], mcp[0] + mcp[2] / 2 - 0.4, mcp[1] + mcp[3],
          style="dotted", color=INK["muted"], lw=1.3)
    # Main -> MCP: routed on the far-left margin (mirrors the Postgres curve)
    # so it never crosses the SpecialistSubgraph container's footprint
    arrow(ax, node_cx(0), node_y, mcp[0] + 0.35, mcp[1] + mcp[3],
          style="dotted", color=INK["muted"], rad=0.9, lw=1.3)
    ax.text(mcp[0] + mcp[2] / 2, mcp[1] + mcp[3] + 0.32,
            "rag ← Specialist · sensor / actuator / ticket ← Main",
            ha="center", va="bottom", fontsize=6.4, color=INK["secondary"], style="italic")

    ax.text(pg[0], pg[1] - 0.22, "← checkpoints (Main), writes (Reflection)",
            fontsize=6.6, color=INK["secondary"], style="italic", ha="left", va="top")
    ax.text(qd[0], qd[1] - 0.22, "← recall + verifier writes (Main), recall (Conversational), writes (Reflection)",
            fontsize=6.6, color=INK["secondary"], style="italic", ha="left", va="top")

    # legend
    lx, ly = 10.5, 8.55
    for i, (style, col, lab) in enumerate([
        ("solid", INK["muted"], "control flow"),
        ("dashed", STATUS["good"], "persistence I/O"),
        ("dotted", INK["muted"], "MCP tool call"),
    ]):
        yy = ly - i * 0.34
        ax.plot([lx, lx + 0.6], [yy, yy], linestyle=style, color=col, lw=1.6)
        ax.text(lx + 0.72, yy, lab, fontsize=7.2, va="center", color=INK["secondary"])

    ax.set_title("System architecture: 3 LangGraphs + 1 shared subgraph over Postgres + Qdrant",
                 fontsize=12.5, fontweight="bold")
    save(fig, "fig-02-system-architecture.png")


# ── fig-06 · evaluation protocol ─────────────────────────────────────────────
def fig06_eval():
    fig, ax = blank((11.0, 3.6))
    ax.set_xlim(-0.2, 10.9); ax.set_ylim(2.9, 8.1)
    box(ax, 0.2, 3.8, 2.3, 2.4, "H1 / H2a / H3\ntasks +\nsimulator\n(ground truth)",
        PALETTE["blue"], fs=8.6)
    box(ax, 3.2, 6.0, 3.0, 1.5, "deterministic anchors\n(numbers, sim root cause)",
        PALETTE["green"], fs=8.3)
    box(ax, 3.2, 3.6, 3.0, 1.5, "dual LLM-judge\n(cross-family, H1 only)", PALETTE["orange"], fs=8.3)
    box(ax, 6.8, 4.6, 3.4, 1.6, "McNemar exact\n(paired) + κ agreement",
        PALETTE["violet"], fs=8.3)
    arrow(ax, 2.5, 5.4, 3.2, 6.6); arrow(ax, 2.5, 4.6, 3.2, 4.3)
    arrow(ax, 6.2, 6.6, 6.8, 5.7); arrow(ax, 6.2, 4.3, 6.8, 5.1)
    ax.set_title("Evaluation protocol: deterministic anchors, checked by a validated dual judge",
                 fontsize=11.8, fontweight="bold")
    save(fig, "fig-06-eval-protocol.png")


if __name__ == "__main__":
    fig01_problem_sdc(); fig04_sensing(); fig05_rag(); fig02_arch(); fig06_eval()
    print("diagrams written")
