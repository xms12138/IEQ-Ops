"""Photo plates: fig-03 (physical deployment), fig-17 (raw readings → natural
language) and fig-27 (the incident lifecycle on the kiosk).

These are evidence photographs of the real exhibit node, so the only operations
applied are geometric and tonal: EXIF auto-orientation, a crop, a projective
rectification of the kiosk screen onto its own plane, and a mild exposure /
saturation normalisation.  No displayed value, glyph or string is ever altered,
added or removed, and nothing from one photograph is composited into another.

Layout follows the same print-first contract as the chart plates (see
`_style.py`): every plate is authored at its FINAL printed width of 6.5 in, so
Word never rescales it and the on-screen text stays legible on the page.  That
constraint is what drives the composition — the kiosk UI is cropped to the one
region each caption is about and given the full text width, instead of showing
the whole 7-inch screen three times at a size no reader can decode.
"""
from __future__ import annotations

import textwrap
from dataclasses import dataclass
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from _style import INK, apply_style

apply_style()
# These plates are laid out in absolute inches, so neither the constrained
# layout engine nor a tight bounding box may touch the authored geometry.
mpl.rcParams["savefig.bbox"] = None

FIG = Path(__file__).resolve().parents[1]  # …/documents/figures

# ── print geometry (values copied from _style, not imported, so this plate is
#    immune to edits in the shared chart style) ────────────────────────────────
W_FULL = 6.5        # authored print width, A4/Letter with 1 in margins
DPI = 300           # → 1950 px wide PNG, sRGB, solid light ground
GAP = 0.16          # gutter between panels in a row
ROW_GAP = 0.20      # gutter between rows
CAP_PAD = 0.06      # panel frame → caption block
CAP_SIZE = 7.6      # panel caption
TAG_INDENT = 0.26   # hanging indent for the bold (a)/(b)/(c) tag
TITLE_SIZE = 9.6
SUB_SIZE = 7.4
FOOT_SIZE = 6.8
_EM = 0.58          # mean advance width of DejaVu Sans, in em
_LEAD = 1.32        # line leading


# ── text metrics ──────────────────────────────────────────────────────────────
def _lh(size: float) -> float:
    """Line height in inches for a given point size."""
    return size * _LEAD / 72


def _wrap(text: str, size: float, width_in: float) -> list[str]:
    ncols = max(16, int(width_in * 72 / (_EM * size) * 0.97))
    out: list[str] = []
    for para in text.split("\n"):
        out.extend(textwrap.wrap(para, ncols) or [""])
    return out


# ── image loading, rectification, tone ────────────────────────────────────────
def _load(name: str) -> Image.Image:
    """EXIF-corrected sRGB image straight from the figures directory."""
    return ImageOps.exif_transpose(Image.open(FIG / name)).convert("RGB")


def _tone(im: Image.Image, contrast: float = 1.0, colour: float = 1.0,
          cut: tuple[float, float] | None = None) -> Image.Image:
    """Exposure normalisation only — no local edits, no retouching."""
    if cut is not None:
        im = ImageOps.autocontrast(im, cutoff=cut)
    if contrast != 1.0:
        im = ImageEnhance.Contrast(im).enhance(contrast)
    if colour != 1.0:
        im = ImageEnhance.Color(im).enhance(colour)
    return im


def _screen_quad(im: Image.Image) -> dict[str, np.ndarray]:
    """Corners of the kiosk's lit UI body, in full-resolution pixel coords.

    The UI ground is light lavender, so a brightness threshold combined with a
    blue-minus-red test separates it from the black bezel, the desk and the
    daylight behind the exhibit.  The largest connected region of that mask is
    the screen; its extreme corners along x±y give the quadrilateral.
    """
    w = 900
    small = im.resize((w, round(im.height * w / im.width)), Image.BILINEAR)
    a = np.asarray(small).astype(np.float32)
    mask = (a.mean(2) > 110) & ((a[:, :, 2] - a[:, :, 0]) > 12)
    try:                                    # keep the largest blob
        from scipy import ndimage
        lab, n = ndimage.label(mask)
        if n > 1:
            sizes = ndimage.sum(mask, lab, range(1, n + 1))
            mask = lab == (1 + int(np.argmax(sizes)))
    except ImportError:                     # fallback: keep the dense core rows/cols
        rows = mask.mean(1) > 0.30
        cols = mask.mean(0) > 0.30
        mask &= rows[:, None] & cols[None, :]
    ys, xs = np.nonzero(mask)
    s, d = xs + ys, xs - ys
    k = im.width / w
    pt = lambda i: np.array([xs[i] * k, ys[i] * k])  # noqa: E731
    return dict(tl=pt(s.argmin()), tr=pt(d.argmax()),
                br=pt(s.argmax()), bl=pt(d.argmin()))


def _rectify(name: str, top_ext: float = 0.095, pad: float = 0.004) -> Image.Image:
    """Map the photographed screen back onto its own plane.

    The detected quad bounds the lit body only, so its top edge is extrapolated
    upward along the two side edges by `top_ext` of the body height to take in
    the dark status bar.  This is a pure projective transform of the whole
    frame — it removes keystone and camera tilt and changes nothing else.
    """
    im = _load(name)
    # The camera sensor's pixel grid beats against the kiosk's own LCD grid and
    # produces moire; a small pre-transform low-pass pass suppresses that beat
    # frequency without touching any displayed value, glyph or string (the
    # quad-detection threshold below is unaffected by this small a blur).
    im = im.filter(ImageFilter.GaussianBlur(radius=1.75))
    q = _screen_quad(im)
    tl = q["tl"] + top_ext * (q["tl"] - q["bl"])
    tr = q["tr"] + top_ext * (q["tr"] - q["br"])
    corners = [tl, q["bl"], q["br"], tr]
    centre = sum(corners) / 4
    tl, bl, br, tr = [c + pad * (c - centre) for c in corners]
    wo = (np.linalg.norm(tr - tl) + np.linalg.norm(br - bl)) / 2
    ho = (np.linalg.norm(bl - tl) + np.linalg.norm(br - tr)) / 2
    out = im.transform((round(wo), round(ho)), Image.QUAD,
                       tuple(np.concatenate([tl, bl, br, tr]).tolist()),
                       resample=Image.BICUBIC)
    return _tone(out, colour=1.06, cut=(0.4, 0.2))


def _crop(im: Image.Image, box: tuple[float, float, float, float],
          rot: float = 0.0) -> Image.Image:
    """Fractional crop (x0, y0, x1, y1), after an optional deskew rotation."""
    if rot:
        im = im.rotate(rot, resample=Image.BICUBIC, expand=False)
    x0, y0, x1, y1 = box
    return im.crop((round(x0 * im.width), round(y0 * im.height),
                    round(x1 * im.width), round(y1 * im.height)))


# ── plate assembly ────────────────────────────────────────────────────────────
@dataclass
class Panel:
    im: Image.Image
    tag: str
    caption: str

    @property
    def aspect(self) -> float:
        return self.im.width / self.im.height


@dataclass
class Row:
    """One band of the plate: panels sized to a common height.

    `cap_side="right"` parks a single panel's caption in the column beside it,
    which is what keeps a wide-but-short photograph from either dominating the
    plate or leaving a dead margin.
    """
    panels: list[Panel]
    cap_side: str = "below"


def _measure(row: Row, width: float) -> tuple[list[float], float, float]:
    """(panel widths, panel height, height of the caption band below)."""
    if row.cap_side == "right":
        p = row.panels[0]
        w = round((width - GAP) * 0.66, 3)
        return [w], w / p.aspect, 0.0
    span = width - GAP * (len(row.panels) - 1)
    h = span / sum(p.aspect for p in row.panels)
    widths = [p.aspect * h for p in row.panels]
    nlines = max(len(_wrap(p.caption, CAP_SIZE, w - TAG_INDENT))
                 for p, w in zip(row.panels, widths))
    return widths, h, CAP_PAD + nlines * _lh(CAP_SIZE)


def _caption(fig, x: float, y: float, w: float, panel: Panel,
             width: float, height: float) -> None:
    """Bold tag with a hanging indent, then the wrapped caption body."""
    fig.text(x / width, y / height, panel.tag, fontsize=CAP_SIZE,
             fontweight="bold", ha="left", va="top", color=INK["primary"])
    for line in _wrap(panel.caption, CAP_SIZE, w - TAG_INDENT):
        fig.text((x + TAG_INDENT) / width, y / height, line, fontsize=CAP_SIZE,
                 ha="left", va="top", color=INK["secondary"])
        y -= _lh(CAP_SIZE)


def _plate(rows: list[Row], title: str, subtitle: str, foot: str,
           name: str, width: float = W_FULL) -> None:
    """Draw stacked rows of equal-height photo panels with hanging captions."""
    sub_lines = _wrap(subtitle, SUB_SIZE, width) if subtitle else []
    foot_lines = _wrap(foot, FOOT_SIZE, width) if foot else []
    head = 0.055 + _lh(TITLE_SIZE) + (0.02 + len(sub_lines) * _lh(SUB_SIZE)
                                      if sub_lines else 0.0) + 0.10
    foot_h = (0.22 + len(foot_lines) * _lh(FOOT_SIZE)) if foot_lines else 0.02

    geom = [_measure(r, width) for r in rows]
    height = head + foot_h + sum(ph + ch for _, ph, ch in geom) \
        + ROW_GAP * (len(rows) - 1)

    fig = plt.figure(figsize=(width, height), facecolor=INK["surface"])
    fig.set_layout_engine("none")

    # title block
    y = height - 0.045
    fig.text(0.0, y / height, title, fontsize=TITLE_SIZE, fontweight="bold",
             ha="left", va="top", color=INK["primary"])
    y -= _lh(TITLE_SIZE) + 0.018
    for line in sub_lines:
        fig.text(0.0, y / height, line, fontsize=SUB_SIZE, ha="left", va="top",
                 color=INK["secondary"])
        y -= _lh(SUB_SIZE)

    # rows, top-down
    top = height - head
    for row, (widths, ph, ch) in zip(rows, geom):
        x = 0.0
        for p, w in zip(row.panels, widths):
            ax = fig.add_axes([x / width, (top - ph) / height,
                               w / width, ph / height])
            # resample once, to the exact printed pixel count
            im = p.im.resize((round(w * DPI), round(ph * DPI)), Image.LANCZOS)
            ax.imshow(np.asarray(im), interpolation="antialiased")
            ax.set_xticks([]); ax.set_yticks([]); ax.grid(False)
            for s in ax.spines.values():
                s.set_visible(True)
                s.set_color(INK["baseline"])
                s.set_linewidth(0.8)
            if row.cap_side == "right":
                _caption(fig, x + w + GAP, top - 0.02, width - w - GAP,
                         p, width, height)
            else:
                _caption(fig, x, top - ph - CAP_PAD, w, p, width, height)
            x += w + GAP
        top -= ph + ch + ROW_GAP

    yf = 0.055
    for line in reversed(foot_lines):
        fig.text(0.0, yf / height, line, fontsize=FOOT_SIZE, ha="left",
                 va="bottom", color=INK["muted"])
        yf += _lh(FOOT_SIZE)

    out = FIG / name
    fig.savefig(out, dpi=DPI, facecolor=INK["surface"])
    plt.close(fig)
    # matplotlib always writes RGBA; the contract asks for an opaque sRGB plate
    with Image.open(out) as png:
        png.convert("RGB").save(out)
    print(f"wrote {name}  ({width:.2f}×{height:.2f} in @ {DPI} dpi)")


# ══ figure 3 ══════════════════════════════════════════════════════════════════
def fig03() -> None:
    kiosk = _crop(_tone(_load("fig17-kiosk-normal.jpg"), contrast=1.05, colour=1.04),
                  (0.030, 0.020, 0.980, 0.928))
    rear = _crop(_tone(_load("fig03-device-rear.jpg"), contrast=1.06, cut=(0.5, 0.5)),
                 (0.425, 0.165, 0.900, 0.625))
    # the panel was shot ~3° off level; deskewing it squares the sensor face
    face = _crop(_tone(_load("fig03-sensor-enclosure.jpg"), contrast=1.08),
                 (0.110, 0.038, 0.865, 0.545), rot=-3.0)

    rows = [
        Row([Panel(kiosk, "(a)",
                   "The node in use — 7-inch touchscreen behind the printed front "
                   "bezel, carry handle above, showing the five channel tiles, the "
                   "current plan and the incident list."),
             Panel(rear, "(b)",
                   "Rear of the same unit: faceted 3D-printed shell, two hexagonal "
                   "honeycomb vent fields, the integrated fan duct and the printed "
                   "stand feet.")]),
        Row([Panel(face, "(c)",
                   "The same enclosure's sensor face: the ANVISION 40 mm fan (left) "
                   "and the Sensirion SCD-30 CO₂ / temperature / humidity board "
                   "(right) — the parts the vent fields and duct in (b) serve.")],
            cap_side="right"),
    ]
    _plate(rows,
           "Physical deployment of the IEQ-Ops exhibit node",
           "One self-contained unit: a Raspberry Pi 4 and a 7-inch touchscreen in a "
           "custom 3D-printed enclosure, with the Arduino MKR WiFi 1010 sensor node "
           "and its SCD-30 behind the ventilated sensor face.",
           "Photographs of the built node — EXIF orientation, crop and exposure "
           "normalisation only.",
           "fig-03-deployment-photos.png")


# ══ figure 17 ═════════════════════════════════════════════════════════════════
def fig17() -> None:
    normal = _rectify("fig17-kiosk-normal.jpg")
    anomaly = _rectify("fig17-kiosk-anomaly.jpg")
    butler = _rectify("fig17-butler-out-of-scope.jpg")

    rows = [
        Row([Panel(_crop(normal, (0.013, 0.118, 0.581, 0.400)), "(a)",
                   "In band — every tile carries its reading, unit and the band it is "
                   "judged against, and all five are ticked (CO₂ 843 ppm, band ≤ 900 "
                   "ppm).")]),
        Row([Panel(_crop(anomaly, (0.013, 0.118, 0.581, 0.420)), "(b)",
                   "Out of band — CO₂ reads 1300 ppm against the same ≤ 900 ppm band "
                   "and its tile turns red with a ⚠; the other four channels stay "
                   "ticked.")]),
        Row([Panel(_crop(anomaly, (0.607, 0.312, 0.977, 0.760)), "(c)",
                   "The same channels put into one sentence, then a question about "
                   "past data answered with a number no tile shows: “27.37 degrees "
                   "Celsius” for last week."),
             Panel(_crop(butler, (0.621, 0.336, 0.983, 0.758)), "(d)",
                   "Guardrail — asked for the capital of China, the butler declines, "
                   "states the limit of its data and redirects to the room.")]),
    ]
    _plate(rows,
           "From raw channel readings to natural language on the kiosk",
           "(a)–(b) the sensor tiles, in band and out of band; (c)–(d) the room "
           "butler putting the same channels into one sentence and answering a "
           "history query, then declining an out-of-scope question.",
           "Photographs of the deployed 7-inch kiosk, rectified onto the screen "
           "plane; no screen content has been altered.",
           "fig-17-raw-vs-nl.png")


# ══ figure 27 ═════════════════════════════════════════════════════════════════
def fig27() -> None:
    normal = _rectify("fig17-kiosk-normal.jpg")
    anomaly = _rectify("fig17-kiosk-anomaly.jpg")
    butler = _rectify("fig17-butler-out-of-scope.jpg")

    rows = [
        Row([Panel(_crop(butler, (0.028, 0.488, 0.612, 0.658)), "(a)",
                   "The plan the kiosk exposes — a single ReWOO subtask for the "
                   "airquality specialist, naming the 1300 ppm reading, the 900 ppm "
                   "WELL threshold and the remediation it must return.")]),
        Row([Panel(_crop(anomaly, (0.018, 0.762, 0.583, 0.982)), "(b)",
                   "OPEN — the CO₂ 1300 ppm incident has reached Plan; Diagnose, Act, "
                   "Verify and Done are still unfilled.")]),
        Row([Panel(_crop(normal, (0.015, 0.757, 0.583, 0.988)), "(c)",
                   "CLOSED — every stage from Detect to Done is filled and the "
                   "verifier's numeric check is recorded underneath as met (Δ−220.6).")]),
    ]
    _plate(rows,
           "The incident lifecycle as the kiosk shows it",
           "Detect → Plan → Diagnose → Act → Verify → Done, with the verifier's "
           "delta written back on closure.",
           "Three separate photographs of the deployed kiosk, not successive frames "
           "of one incident; rectified onto the screen plane, with no screen content "
           "altered.",
           "fig-27-kiosk-incident-lifecycle.png")


if __name__ == "__main__":
    fig03()
    fig17()
    fig27()
    print("photo composites done")
