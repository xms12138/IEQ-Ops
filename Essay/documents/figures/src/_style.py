"""Shared dissertation figure style — one visual system for every plate.

Design contract (see FIGURE_MANIFEST.md "产图规范"):
  * print-first sizing — every figure is authored at its FINAL printed width
    (FULL_W = 6.5 in fits A4/Letter with 1 in margins), so nothing is rescaled
    in Word and no font ever shrinks below ~7 pt on the page;
  * one restrained palette, CVD-validated with the dataviz skill's
    `scripts/validate_palette.py` (light mode, surface #fcfcfb);
  * meaning is never carried by hue alone — every colour is paired with
    position, glyph or a direct label, so the plates survive greyscale
    photocopying;
  * grid and spines are recessive and always *behind* the marks
    (`axes.axisbelow`), titles are left-aligned with a muted subtitle line
    that carries n and the data source.

Palette provenance
------------------
Categorical slots come from the dataviz reference palette; the four IEQ
domains use the validated order blue → orange → aqua → violet
(worst adjacent ΔE 27.6 normal / 9.2 deutan — PASS).
STATUS is a reserved good/warning/critical trio, re-stepped darker than the
reference so every step clears 3:1 contrast on the paper surface; green↔amber
sits in the 6–8 CVD floor band, which is legal only with secondary encoding, so
status marks in this dissertation ALWAYS ship with a glyph and a word.
Ordered/pipeline stages use the sequential blue ramp, never categorical hues.
"""
from __future__ import annotations

import matplotlib as mpl
import matplotlib.pyplot as plt

# ── print geometry ────────────────────────────────────────────────────────────
FULL_W = 6.5    # full text width, A4/Letter with 1in margins
HALF_W = 3.15   # two figures side by side
DPI = 300

# ── categorical slots (fixed order — never cycled) ────────────────────────────
PALETTE = {
    "blue": "#2a78d6",
    "orange": "#eb6834",
    "aqua": "#1baf7a",
    "violet": "#4a3aa7",
    "magenta": "#e87ba4",
    "yellow": "#eda100",
    "green": "#008300",
    "red": "#e34948",
}
# The four IEQ domains, in the validated adjacency order.
DOMAIN = {
    "airquality": PALETTE["blue"],
    "thermal": PALETTE["orange"],
    "lighting": PALETTE["yellow"],
    "acoustic": PALETTE["violet"],
}
DOMAIN_MARK = {"airquality": "o", "thermal": "s", "lighting": "^", "acoustic": "D"}

# ── status palette (reserved; always shipped with a glyph + word) ─────────────
STATUS = {
    "good": "#1f7a3f",
    "warning": "#c07a09",
    "serious": "#cf6a2a",
    "critical": "#b8322e",
}
GLYPH = {"good": "✓", "warning": "!", "critical": "✗", "held": "‖"}

# ── ink / chrome ──────────────────────────────────────────────────────────────
INK = {
    "surface": "#fcfcfb",
    "panel": "#f4f3ef",     # very light fill for reference bands / card backs
    "primary": "#121211",
    "secondary": "#4f4e4a",
    "muted": "#86847e",
    "grid": "#e4e3dc",
    "baseline": "#bfbeb3",
    "rule": "#d5d4cb",
}
# Ordered / pipeline stages: sequential ramp (light → dark), never a rainbow.
SEQ_BLUE = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
# Paired-condition convention used across every ablation plate in this set:
# the baseline arm is inert grey, the treatment arm is the one saturated hue.
OFF_C = "#9a9891"
ON_C = PALETTE["blue"]

FIG_DIR = __file__.rsplit("/", 1)[0].rsplit("/src", 1)[0]  # …/documents/figures


def apply_style() -> None:
    mpl.rcParams.update({
        "figure.facecolor": INK["surface"],
        "axes.facecolor": INK["surface"],
        "savefig.facecolor": INK["surface"],
        "savefig.dpi": DPI,
        "savefig.bbox": None,
        "font.family": "DejaVu Sans",
        "font.size": 8.0,
        "text.color": INK["primary"],
        "axes.labelcolor": INK["secondary"],
        "axes.labelsize": 8.0,
        "axes.edgecolor": INK["baseline"],
        "axes.linewidth": 0.7,
        "axes.titlecolor": INK["primary"],
        "axes.titlesize": 8.8,
        "axes.titleweight": "bold",
        "axes.titlepad": 4.0,
        "axes.axisbelow": True,          # grid never draws over the marks
        "axes.grid": True,
        "axes.grid.axis": "y",
        "grid.color": INK["grid"],
        "grid.linewidth": 0.6,
        "xtick.color": INK["secondary"],
        "ytick.color": INK["secondary"],
        "xtick.labelsize": 7.5,
        "ytick.labelsize": 7.5,
        "xtick.major.size": 2.5,
        "ytick.major.size": 2.5,
        "xtick.major.width": 0.7,
        "ytick.major.width": 0.7,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "legend.frameon": False,
        "legend.fontsize": 7.5,
        "legend.handlelength": 1.4,
        "legend.columnspacing": 1.2,
        "lines.linewidth": 1.6,
        "lines.markersize": 4.5,
        "figure.constrained_layout.use": True,
        "figure.constrained_layout.h_pad": 0.03,
        "figure.constrained_layout.w_pad": 0.03,
        "svg.fonttype": "none",
        "hatch.linewidth": 0.6,
    })


# ── titling & plate layout ───────────────────────────────────────────────────
# Text is wrapped to the authored print width and the layout engine is given an
# explicit rect, so the header/footer bands can never collide with the axes and
# the saved PNG is exactly FULL_W wide (no tight-bbox expansion).
_EM = 0.58          # mean advance width of DejaVu Sans, in em
_LEAD = 1.32        # line leading


def _wrap(text: str, fontsize: float, width_in: float) -> list[str]:
    import textwrap
    ncols = max(20, int(width_in * 72 / (_EM * fontsize) * 0.97))
    out: list[str] = []
    for para in text.split("\n"):
        out.extend(textwrap.wrap(para, ncols) or [""])
    return out


def layout(fig, title: str, subtitle: str = "", foot: str = "",
           title_size: float = 9.6, sub_size: float = 7.4, foot_size: float = 6.8):
    """Draw the title block and source footnote, reserving space for both.

    Keeps every plate in the set typographically identical: bold sentence-case
    title, muted subtitle carrying n and the experimental condition, and a muted
    source/caveat line so each figure reads standing alone.
    """
    w, h = fig.get_size_inches()
    sub_lines = _wrap(subtitle, sub_size, w) if subtitle else []
    foot_lines = _wrap(foot, foot_size, w) if foot else []

    head_in = 0.055 + title_size * _LEAD / 72
    if sub_lines:
        head_in += 0.02 + len(sub_lines) * sub_size * _LEAD / 72
    head_in += 0.19          # clearance for panel titles / value labels
    foot_in = (0.10 + len(foot_lines) * foot_size * _LEAD / 72) if foot_lines else 0.02

    eng = fig.get_layout_engine()
    if eng is not None:
        # rect is (x0, y0, width, height) in figure fractions
        eng.set(rect=(0.0, foot_in / h, 1.0, 1.0 - (head_in + foot_in) / h))

    y = 1.0 - 0.045 / h
    fig.text(0.0, y, title, fontsize=title_size, fontweight="bold", ha="left",
             va="top", color=INK["primary"])
    y -= title_size * _LEAD / 72 / h + 0.018 / h
    for line in sub_lines:
        fig.text(0.0, y, line, fontsize=sub_size, ha="left", va="top",
                 color=INK["secondary"])
        y -= sub_size * _LEAD / 72 / h
    yf = 0.055 / h          # bottom margin; lines stack upward inside foot_in
    for line in reversed(foot_lines):
        fig.text(0.0, yf, line, fontsize=foot_size, ha="left", va="bottom",
                 color=INK["muted"])
        yf += foot_size * _LEAD / 72 / h
    # usable vertical band, for plates that place their axes manually
    return foot_in / h, 1.0 - head_in / h


def titles(fig, title: str, subtitle: str = "", y: float = 1.0) -> None:
    """Back-compat shim — prefer layout()."""
    layout(fig, title, subtitle)


def ax_title(ax, title: str, subtitle: str = "") -> None:
    """Panel-level title + optional muted second line (used in small multiples)."""
    ax.set_title(title, fontsize=8.2, fontweight="bold", loc="left", pad=3)
    if subtitle:
        ax.text(0.0, 1.012, subtitle, transform=ax.transAxes, fontsize=7.0,
                va="bottom", ha="left", color=INK["secondary"])


def footnote(fig, text: str, y: float = -0.005) -> None:
    """Deprecated — layout() draws the footnote inside the reserved band."""
    return None


def despine(ax, left: bool = False, bottom: bool = False) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    if left:
        ax.spines["left"].set_visible(False)
    if bottom:
        ax.spines["bottom"].set_visible(False)


# ── uncertainty ───────────────────────────────────────────────────────────────
def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion.

    Used instead of a normal approximation because several IEQ-Bench cells have
    n as small as 2 — the interval is derived from the reported k/n, it does not
    alter any reported point estimate.
    """
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return (max(0.0, (c - h) / d), min(1.0, (c + h) / d))


def mcnemar_exact_p(b: int, c: int) -> float:
    """Two-sided exact (binomial) McNemar p for a b:c discordant split."""
    from math import comb
    n = b + c
    if n == 0:
        return 1.0
    lo = min(b, c)
    tail = sum(comb(n, i) for i in range(lo + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


# ── output ────────────────────────────────────────────────────────────────────
def save(fig, name: str) -> str:
    """Write the manifest-contracted PNG plus a vector .svg alongside it."""
    path = f"{FIG_DIR}/{name}"
    fig.savefig(path)
    if name.endswith(".png"):
        fig.savefig(path[:-4] + ".svg")
    plt.close(fig)
    return path
