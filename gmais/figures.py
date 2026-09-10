"""Publication figures for the GMAIS evaluation (Sections 3.3.4-3.3.7).

Every figure is rendered from the observation matrix of an actual campaign --
there are no illustrative or schematic data values anywhere in this module. Each
is written as vector PDF (for the thesis) and 300 dpi PNG (for review copies).

Encoding
--------
The design is a 2x2 factorial, so the figures encode it as one:

* **Hue carries Validation** -- one cool slot for V=0, one warm slot for V=1.
* **Texture carries Governance** -- solid for G=0, hatched for G=1.

Two hues rather than four means the palette clears the colour-vision-deficiency
separation floors with room to spare, and the hatch is a second, fully
non-chromatic channel: the figures stay readable in greyscale print and under
any form of colour blindness. Bars additionally carry direct value labels, which
discharges the contrast-relief requirement for the lighter slots.

Uncertainty is drawn wherever it exists. Bars carry 95% bootstrap intervals
resampled over scenarios; distributions are drawn as violins with the quartile
box inside them, never as a bar of means with the spread thrown away.
"""

from __future__ import annotations

import math
import os
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")  # headless: figures are files, never windows
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Patch  # noqa: E402

from .ablation import AblationResult  # noqa: E402
from .hypotheses import align, test_h4  # noqa: E402
from .stats import (  # noqa: E402
    CELL_ORDER,
    bootstrap_ci,
    brier_decomposition,
    _mean,
    _median,
    _quantile,
)

# --------------------------------------------------------------------------- #
# Design tokens (validated categorical palette; see references/palette.md)
# --------------------------------------------------------------------------- #
SURFACE = "#fcfcfb"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#8a8983"
GRID = "#e3e2dd"

HUE_V0 = "#2a78d6"  # slot 1, blue  - Validation absent
HUE_V1 = "#eb6834"  # slot 2, orange - Validation present
HUE_ACCENT = "#1baf7a"  # slot 3, aqua - measured-quantity series

#: cell -> (facecolour, hatch). Governance is carried entirely by texture.
CELL_STYLE: Dict[str, Tuple[str, str]] = {
    "Baseline": (HUE_V0, ""),
    "G-only": (HUE_V0, "///"),
    "V-only": (HUE_V1, ""),
    "Full": (HUE_V1, "///"),
}
#: Left-to-right order for the factorial panels: governance varies within
#: validation, so the two hue groups stay adjacent and readable.
PLOT_ORDER = ("Baseline", "G-only", "V-only", "Full")

BAND_COLOURS = {
    "full-governance": "#dceee4",
    "adaptive-governance": "#fdf0e6",
    "minimal-governance": "#fbe0e0",
}


def _apply_style() -> None:
    plt.rcParams.update({
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "font.family": "DejaVu Sans",
        "font.size": 9,
        "axes.titlesize": 10,
        "axes.titleweight": "bold",
        "axes.labelsize": 9,
        "axes.labelcolor": INK_SECONDARY,
        "axes.edgecolor": GRID,
        "axes.linewidth": 0.8,
        "axes.grid": True,
        "axes.axisbelow": True,
        "grid.color": GRID,
        "grid.linewidth": 0.6,
        "xtick.color": INK_SECONDARY,
        "ytick.color": INK_SECONDARY,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.frameon": False,
        "legend.fontsize": 8,
        "hatch.linewidth": 0.7,
    })


def _despine(ax) -> None:
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.grid(axis="x", visible=False)


def _factorial_legend(fig, loc: str = "lower center", ncol: int = 4) -> None:
    handles = [
        Patch(facecolor=HUE_V0, edgecolor="white", label="Baseline  (V0 G0)"),
        Patch(facecolor=HUE_V0, edgecolor="white", hatch="///", label="G-only  (V0 G1)"),
        Patch(facecolor=HUE_V1, edgecolor="white", label="V-only  (V1 G0)"),
        Patch(facecolor=HUE_V1, edgecolor="white", hatch="///", label="Full GMAIS  (V1 G1)"),
    ]
    fig.legend(handles=handles, loc=loc, ncol=ncol, bbox_to_anchor=(0.5, -0.075))


def _save(fig, outdir: str, stem: str) -> List[str]:
    os.makedirs(outdir, exist_ok=True)
    paths = []
    for ext in ("pdf", "png"):
        path = os.path.join(outdir, f"{stem}.{ext}")
        fig.savefig(path, dpi=300, bbox_inches="tight")
        paths.append(path)
    plt.close(fig)
    return paths


def _ci_for(values: Sequence[float], seed: int, statistic=_mean):
    interval = bootstrap_ci(values, statistic, seed=seed, n_boot=2000)
    return interval.estimate, interval.estimate - interval.low, interval.high - interval.estimate


# --------------------------------------------------------------------------- #
# Figure 1 - system architecture
# --------------------------------------------------------------------------- #
def figure_architecture(outdir: str) -> List[str]:
    """Figure 1: the GMAIS two-tier topology with governance mediation.

    Drawn as vector geometry rather than exported from a diagramming tool, so it
    scales without resampling artefacts and every label is selectable text at
    full resolution. This replaces the raster Figure 1, whose legibility the
    review flagged.
    """

    _apply_style()
    fig, ax = plt.subplots(figsize=(9.6, 6.6))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")

    # Layout constants. Box heights are computed from content rather than
    # hand-tuned, so no label can overflow its container.
    TITLE_PAD, LINE_H, BOTTOM_PAD = 5.4, 3.5, 2.6
    BODY_SIZE, TITLE_SIZE = 7.2, 9.0

    def box_height(lines: Sequence[str]) -> float:
        return TITLE_PAD + len(lines) * LINE_H + BOTTOM_PAD

    def box(x, y, w, lines, title, face, edge):
        """Draw a titled box whose height is derived from its own content."""

        h = box_height(lines)
        ax.add_patch(FancyBboxPatch(
            (x, y), w, h, boxstyle="round,pad=0.55,rounding_size=1.2",
            facecolor=face, edgecolor=edge, linewidth=1.3,
        ))
        ax.text(x + w / 2, y + h - 1.6, title, ha="center", va="top",
                fontsize=TITLE_SIZE, fontweight="bold", color=INK_PRIMARY)
        for i, line in enumerate(lines):
            ax.text(x + w / 2, y + h - TITLE_PAD - 1.0 - i * LINE_H, line,
                    ha="center", va="top", fontsize=BODY_SIZE, color=INK_SECONDARY)
        return h

    def arrow(xy_from, xy_to, colour=INK_SECONDARY, rad=0.0, dashed=False,
              style="-|>"):
        ax.add_patch(FancyArrowPatch(
            xy_from, xy_to, arrowstyle=style, mutation_scale=11,
            linewidth=1.1, color=colour, linestyle="--" if dashed else "-",
            connectionstyle=f"arc3,rad={rad}", shrinkA=1, shrinkB=1, zorder=2,
        ))

    def flow_label(x, y, text, colour=INK_SECONDARY, ha="left"):
        ax.text(x, y, text, ha=ha, va="center", fontsize=6.9, color=colour,
                style="italic", zorder=3)

    # --- Column geometry -------------------------------------------------- #
    LEFT_X, LEFT_W = 19.0, 37.0        # analytical pipeline
    GAP_X = LEFT_X + LEFT_W            # 56.0 — routing channel
    RIGHT_X, RIGHT_W = 66.0, 33.0      # Governance Layer
    CX = LEFT_X + LEFT_W / 2           # left-column centre line

    # --- Input ------------------------------------------------------------ #
    TOP = 90.0
    in_lines = ["complexity-stratified,", "normalised claim set", "(Section 3.2.2)"]
    in_h = box_height(in_lines)
    box(0.5, TOP - in_h, 16.0, in_lines, "OSINT scenario", "#f2f1ec", GRID)

    # --- Left column ------------------------------------------------------ #
    orch_lines = ["apex of the web-of-intelligence", "topology; runs all four cells"]
    orch_h = box_height(orch_lines)
    orch_y = TOP - orch_h
    box(LEFT_X, orch_y, LEFT_W, orch_lines, "ORCHESTRATOR", "#eaf1fb", HUE_V0)

    work_lines = ["3 concurrent agents (T = 0.7);", "no source validation;",
                  "peer exchange carries entities"]
    work_h = box_height(work_lines)
    work_y = orch_y - 6.5 - work_h
    box(LEFT_X, work_y, LEFT_W, work_lines, "WORKER TIER", "#eaf1fb", HUE_V0)

    val_lines = ["Admiralty grading, two axes", "ACH + Heuer diagnosticity",
                 "bounded-rationality halt at", "convergence ≥ 0.85 or CI < 0.15"]
    val_h = box_height(val_lines)
    val_y = work_y - 8.0 - val_h
    box(LEFT_X, val_y, LEFT_W, val_lines, "VALIDATOR   (T = 0.2)", "#fdeee7", HUE_V1)

    out_lines = ["hypothesis + calibrated confidence"]
    out_h = box_height(out_lines)
    out_y = val_y - 6.5 - out_h
    box(LEFT_X, out_y, LEFT_W, out_lines, "Graded analytical product",
        "#f2f1ec", GRID)

    # --- Governance Layer -------------------------------------------------- #
    # Sized so the box spans the full vertical extent of the agent tiers it
    # mediates: every arrow into it lands inside the box, not beside it.
    gov_lines = [
        "asynchronous mediation queue",
        "delegation tokens: HMAC-SHA256",
        "",
        "fG(e) = 1 iff all three hold:",
        "1.  delegation token verifies",
        "2.  need-to-know satisfied",
        "3.  sensitivity ≤ threshold",
        "P(compliance | e) ≥ θ = 0.60",
        "",
        "named-entity redaction on",
        "worker-to-worker traffic",
        "",
        "SHA-256 hash-chained audit log",
    ]
    gov_h = box_height(gov_lines)
    gov_y = TOP - gov_h
    box(RIGHT_X, gov_y, RIGHT_W, gov_lines, "GOVERNANCE LAYER   G",
        "#e6f6ef", HUE_ACCENT)

    # --- Vertical pipeline flows ------------------------------------------ #
    for y_top, y_bot, label in (
        (orch_y, work_y + work_h, "tasking"),
        (work_y, val_y + val_h, "worker synthesis"),
        (val_y, out_y + out_h, "validated product"),
    ):
        arrow((CX, y_top), (CX, y_bot))
        flow_label(CX - 1.6, (y_top + y_bot) / 2, label, ha="right")

    arrow((16.9, orch_y + orch_h / 2), (LEFT_X - 0.4, orch_y + orch_h / 2))

    # --- Governance mediation channel (routed through the gap) ------------- #
    # Labels are kept short enough to sit inside the 10-unit routing channel;
    # the event tuple is expanded in the caption rather than on the arrow.
    gov_flows = [
        (work_y + work_h * 0.70, "events e", True),
        (work_y + work_h * 0.26, "fG(e)", False),
        (val_y + val_h * 0.78, "critique e", True),
    ]
    for y, label, outbound in gov_flows:
        if outbound:
            arrow((GAP_X + 0.4, y), (RIGHT_X - 0.4, y), colour=HUE_ACCENT)
        else:
            arrow((RIGHT_X - 0.4, y), (GAP_X + 0.4, y), colour=HUE_ACCENT)
        flow_label((GAP_X + RIGHT_X) / 2, y + 2.2, label, colour=HUE_ACCENT,
                   ha="center")

    # --- Worker-to-worker peer loop (left margin) --------------------------- #
    peer_y = work_y + work_h / 2
    ax.add_patch(FancyArrowPatch(
        (LEFT_X - 0.4, peer_y + 3.0), (LEFT_X - 0.4, peer_y - 3.0),
        arrowstyle="<|-|>", mutation_scale=10, linewidth=1.2, color=HUE_V0,
        connectionstyle="arc3,rad=0.9", zorder=2,
    ))
    ax.text(8.5, peer_y, "peer exchange\n(entity-redacted\nunder governance)",
            ha="center", va="center", fontsize=6.9, color=HUE_V0, style="italic")

    # --- Validator critique loop back to the Worker tier -------------------- #
    loop_x = LEFT_X + LEFT_W * 0.82
    arrow((loop_x, val_y + val_h), (loop_x, work_y), colour=HUE_V1, dashed=True)
    ax.text(loop_x + 1.4, (val_y + val_h + work_y) / 2,
            "critique /\ncorrection\nloop", ha="left", va="center", fontsize=6.6,
            color=HUE_V1, style="italic")

    # --- Factorial-design inset (bottom right, clear of every box) ---------- #
    # Swatch carries the identity; the label wears text ink, so the hatch never
    # cuts through a glyph.
    inset_y = 5.0
    ax.text(RIGHT_X, inset_y + 17.0, "The 2 × 2 ablation", fontsize=8.2,
            fontweight="bold", color=INK_PRIMARY, ha="left")
    ax.text(RIGHT_X, inset_y + 13.0, "hue = validation · hatch = governance",
            fontsize=6.8, color=INK_MUTED, ha="left", style="italic")
    for name, cx, cy in (("Baseline", RIGHT_X, inset_y + 5.6),
                         ("G-only", RIGHT_X + 17.0, inset_y + 5.6),
                         ("V-only", RIGHT_X, inset_y),
                         ("Full GMAIS", RIGHT_X + 17.0, inset_y)):
        key = "Full" if name == "Full GMAIS" else name
        face, hatch = CELL_STYLE[key]
        ax.add_patch(FancyBboxPatch(
            (cx, cy), 4.4, 4.0, boxstyle="round,pad=0.1,rounding_size=0.5",
            facecolor=face, edgecolor="white", linewidth=1.0, hatch=hatch,
        ))
        code = f"V{int(key in ('V-only', 'Full'))}G{int(key in ('G-only', 'Full'))}"
        ax.text(cx + 5.6, cy + 2.0, f"{name}  ({code})", ha="left", va="center",
                fontsize=7.0, color=INK_PRIMARY)

    ax.text(50, 97.5, "Figure 1  GMAIS architecture: a two-tier multi-agent "
            "topology under asynchronous governance mediation",
            ha="center", va="center", fontsize=10.5, fontweight="bold",
            color=INK_PRIMARY)
    ax.text(50, 93.4, "M = ⟨A, S, E, G, P⟩ (Section 3.3.1).  Each event "
            "e = ⟨m, t, c⟩ is a payload m at timestamp t with token context c.  "
            "Green paths are governance-mediated: every inter-agent event is "
            "policy-evaluated,\nneed-to-know filtered and appended to the "
            "hash-chained audit log.",
            ha="center", va="center", fontsize=7.4, color=INK_MUTED,
            linespacing=1.5)

    return _save(fig, outdir, "fig01_architecture")


# --------------------------------------------------------------------------- #
# Figure 2 - ablation performance
# --------------------------------------------------------------------------- #
def figure_ablation_performance(result: AblationResult, outdir: str) -> List[str]:
    """Figure 2: analytical performance across the four factorial cells."""

    _apply_style()
    seed = result.config.seed
    acc = align(result, "correct")
    conf = align(result, "confidence")
    rubric = align(result, "rubric_composite")

    panels = [
        ("Hypothesis accuracy", acc, "proportion correct", (0, 1.05)),
        ("GTKG rubric composite", rubric, "graded score", (0, 1.05)),
    ]

    fig, axes = plt.subplots(1, 3, figsize=(10.5, 3.6))

    for ax, (title, data, ylabel, ylim) in zip(axes[:2], panels):
        _despine(ax)
        for i, cell in enumerate(PLOT_ORDER):
            face, hatch = CELL_STYLE[cell]
            value, lo, hi = _ci_for(data[cell], seed)
            ax.bar(i, value, width=0.62, color=face, hatch=hatch,
                   edgecolor="white", linewidth=1.4)
            ax.errorbar(i, value, yerr=[[lo], [hi]], fmt="none",
                        ecolor=INK_PRIMARY, elinewidth=1.1, capsize=3.5)
            ax.text(i, value + hi + 0.035, f"{value:.3f}", ha="center",
                    va="bottom", fontsize=7.4, color=INK_PRIMARY)
        ax.set_xticks(range(4))
        ax.set_xticklabels(PLOT_ORDER, rotation=12)
        ax.set_ylim(*ylim)
        ax.set_ylabel(ylabel)
        ax.set_title(title)

    # Detection: precision / recall / F1 at claim level.
    ax = axes[2]
    _despine(ax)
    metrics = ("precision", "recall", "f1")
    width = 0.2
    for i, cell in enumerate(PLOT_ORDER):
        face, hatch = CELL_STYLE[cell]
        detection = result.per_cell_metrics[cell]["detection"]
        values = [detection[m] for m in metrics]
        xs = [j + (i - 1.5) * width for j in range(len(metrics))]
        ax.bar(xs, values, width=width * 0.9, color=face, hatch=hatch,
               edgecolor="white", linewidth=1.0)
    ax.set_xticks(range(len(metrics)))
    ax.set_xticklabels(["Precision", "Recall", "F1"])
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("claim-level score")
    ax.set_title("Misinformation detection")

    fig.suptitle("Figure 2  Analytical performance by factorial cell "
                 f"(N = {len(result.observations)} observations, "
                 "95% bootstrap CIs over scenarios)",
                 fontsize=10, fontweight="bold", color=INK_PRIMARY, y=1.06)
    _factorial_legend(fig)
    fig.tight_layout()
    return _save(fig, outdir, "fig02_ablation_performance")


# --------------------------------------------------------------------------- #
# Figure 3 - cost overhead
# --------------------------------------------------------------------------- #
def figure_overhead(result: AblationResult, outdir: str) -> List[str]:
    """Figure 3: latency and token cost by cell and complexity tier.

    Latency and tokens are on separate axes in separate panels -- never a second
    y-scale on one plot, which would invent a relationship between them.
    """

    _apply_style()
    seed = result.config.seed
    lat = align(result, "latency_ms")
    tok = align(result, "tokens")

    fig, axes = plt.subplots(1, 3, figsize=(11.0, 3.6))

    for ax, data, title, ylabel in (
        (axes[0], lat, "End-to-end latency", "milliseconds (modelled)"),
        (axes[1], tok, "Token consumption", "tokens per observation"),
    ):
        _despine(ax)
        for i, cell in enumerate(PLOT_ORDER):
            face, hatch = CELL_STYLE[cell]
            value, lo, hi = _ci_for(data[cell], seed)
            ax.bar(i, value, width=0.62, color=face, hatch=hatch,
                   edgecolor="white", linewidth=1.4)
            ax.errorbar(i, value, yerr=[[lo], [hi]], fmt="none",
                        ecolor=INK_PRIMARY, elinewidth=1.1, capsize=3.5)
            ax.text(i, value + hi, f"{value:,.0f}", ha="center", va="bottom",
                    fontsize=7.4, color=INK_PRIMARY)
        ax.set_xticks(range(4))
        ax.set_xticklabels(PLOT_ORDER, rotation=12)
        ax.set_ylabel(ylabel)
        ax.set_title(title)

    # Governance overhead by tier: does the tax scale with problem complexity?
    ax = axes[2]
    _despine(ax)
    tiers = ["low", "medium", "high"]
    by_tier = {t: {} for t in tiers}
    for obs in result.observations:
        by_tier[obs.tier].setdefault(obs.cell, []).append(obs.latency_ms)

    ungoverned = [
        _mean(by_tier[t]["Baseline"] + by_tier[t]["V-only"]) for t in tiers
    ]
    governed = [
        _mean(by_tier[t]["G-only"] + by_tier[t]["Full"]) for t in tiers
    ]
    overhead = [g - u for g, u in zip(governed, ungoverned)]
    ax.bar(range(3), overhead, width=0.55, color=HUE_ACCENT,
           edgecolor="white", linewidth=1.4)
    for i, value in enumerate(overhead):
        ax.text(i, value, f"+{value:.1f} ms", ha="center", va="bottom",
                fontsize=7.4, color=INK_PRIMARY)
    ax.set_xticks(range(3))
    ax.set_xticklabels([t.capitalize() for t in tiers])
    ax.set_ylabel("added latency (ms)")
    ax.set_title("Governance overhead by tier")

    fig.suptitle("Figure 3  The cost side of the Security Tax: governance raises "
                 "both latency and token consumption",
                 fontsize=10, fontweight="bold", color=INK_PRIMARY, y=1.06)
    _factorial_legend(fig)
    fig.tight_layout()
    return _save(fig, outdir, "fig03_overhead")


# --------------------------------------------------------------------------- #
# Figure 4 - Security Tax distribution
# --------------------------------------------------------------------------- #
def figure_security_tax(result: AblationResult, outdir: str) -> List[str]:
    """Figure 4: the Security-Tax distribution against the policy bands.

    Drawn as violins with quartile boxes rather than bars of means: H4 is a claim
    about where a *distribution* sits relative to two thresholds, so the spread
    is the substance of the figure, not decoration.
    """

    _apply_style()
    cfg = result.config

    by_cell: Dict[str, List[float]] = {}
    for st in result.security_tax:
        by_cell.setdefault(st.cell, []).append(st.security_tax)

    fig, (ax, ax2) = plt.subplots(
        1, 2, figsize=(10.5, 4.2), gridspec_kw={"width_ratios": [1.55, 1]}
    )
    _despine(ax)

    values = [by_cell[c] for c in PLOT_ORDER]
    lo = min(min(v) for v in values)
    hi = max(max(v) for v in values)
    pad = 0.35 * (hi - lo) if hi > lo else 1.0

    # Policy bands as background regions, labelled once on the right margin.
    ax.axhspan(lo - pad, cfg.st_band_low, color=BAND_COLOURS["full-governance"], zorder=0)
    ax.axhspan(cfg.st_band_low, cfg.st_band_high,
               color=BAND_COLOURS["adaptive-governance"], zorder=0)
    ax.axhspan(cfg.st_band_high, hi + pad,
               color=BAND_COLOURS["minimal-governance"], zorder=0)
    for y, label in ((cfg.st_band_low, f"ST = {cfg.st_band_low}"),
                     (cfg.st_band_high, f"ST = {cfg.st_band_high}")):
        ax.axhline(y, color=INK_MUTED, linewidth=0.9, linestyle="--", zorder=1)
        ax.text(4.62, y, label, fontsize=7, color=INK_SECONDARY,
                va="center", ha="left")

    # Band labels sit at the mid-height of the *visible* portion of each band,
    # so none of them lands on a threshold line or on the median row above.
    y_bottom, y_top = lo - pad, hi + pad
    band_regions = [
        (y_bottom, min(cfg.st_band_low, y_top),
         "full governance\n(ST < %.1f)" % cfg.st_band_low),
        (max(cfg.st_band_low, y_bottom), min(cfg.st_band_high, y_top),
         "adaptive\ngovernance"),
        (max(cfg.st_band_high, y_bottom), y_top, "minimal\ngovernance"),
    ]
    # Anchored to the TOP of each band rather than its middle: the violins sit
    # near the middle of the band they fall in, so a centred label collides with
    # the leftmost one. The top of a band is always free.
    for band_lo, band_hi, label in band_regions:
        if band_hi - band_lo < 0.08 * (y_top - y_bottom):
            continue  # too thin to label without colliding
        ax.text(0.38, band_hi - 0.03 * (y_top - y_bottom), label, fontsize=7,
                color=INK_MUTED, va="top", ha="left", linespacing=1.35)

    parts = ax.violinplot(values, positions=range(1, 5), widths=0.72,
                          showextrema=False, showmedians=False)
    for body, cell in zip(parts["bodies"], PLOT_ORDER):
        face, hatch = CELL_STYLE[cell]
        body.set_facecolor(face)
        body.set_edgecolor("white")
        body.set_linewidth(1.2)
        body.set_alpha(0.85)
        if hatch:
            body.set_hatch(hatch)

    box = ax.boxplot(values, positions=range(1, 5), widths=0.16,
                     showfliers=False, patch_artist=True, zorder=3)
    for patch in box["boxes"]:
        patch.set_facecolor(SURFACE)
        patch.set_edgecolor(INK_PRIMARY)
        patch.set_linewidth(0.9)
    for key in ("whiskers", "caps", "medians"):
        for line in box[key]:
            line.set_color(INK_PRIMARY)
            line.set_linewidth(1.0)

    # Anchor each median label to its own violin rather than to a shared top
    # row, so the labels cannot drift into a band label or a threshold line.
    for i, cell in enumerate(PLOT_ORDER, start=1):
        values = by_cell[cell]
        ax.text(i, max(values) + pad * 0.18, f"Mdn {_median(values):+.2f}",
                ha="center", va="bottom", fontsize=7.2, color=INK_PRIMARY)

    ax.set_xticks(range(1, 5))
    ax.set_xticklabels(PLOT_ORDER, rotation=12)
    ax.set_xlim(0.3, 4.6)
    ax.set_ylim(lo - pad, hi + pad)
    ax.set_ylabel(f"Security Tax\nST = {cfg.st_alpha:g}·z(ΔL) + {cfg.st_beta:g}·z(ΔC)",
                  linespacing=1.6)
    ax.set_title("Security-Tax distribution by cell")

    # Right panel: how each cell's observations distribute across the bands.
    _despine(ax2)
    band_order = ("full-governance", "adaptive-governance", "minimal-governance")
    bottoms = [0.0] * len(PLOT_ORDER)
    for band in band_order:
        heights = []
        for cell in PLOT_ORDER:
            n = len(by_cell[cell])
            k = sum(1 for st in result.security_tax
                    if st.cell == cell and st.band == band)
            heights.append(100.0 * k / n if n else 0.0)
        ax2.bar(range(len(PLOT_ORDER)), heights, bottom=bottoms, width=0.62,
                color=BAND_COLOURS[band], edgecolor=SURFACE, linewidth=2.0,
                label=band.replace("-", " "))
        for i, (h, b) in enumerate(zip(heights, bottoms)):
            if h >= 8:
                ax2.text(i, b + h / 2, f"{h:.0f}%", ha="center", va="center",
                         fontsize=7.2, color=INK_PRIMARY)
        bottoms = [b + h for b, h in zip(bottoms, heights)]

    ax2.set_xticks(range(len(PLOT_ORDER)))
    ax2.set_xticklabels(PLOT_ORDER, rotation=12)
    ax2.set_ylim(0, 100)
    ax2.set_ylabel("% of observations")
    ax2.set_title("Policy-band assignment")
    ax2.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=1)

    fig.suptitle("Figure 4  H4: Security-Tax distribution and its mapping onto "
                 "pre-registered governance-policy bands",
                 fontsize=10, fontweight="bold", color=INK_PRIMARY, y=1.03)
    fig.tight_layout()
    return _save(fig, outdir, "fig04_security_tax")


# --------------------------------------------------------------------------- #
# Figure 5 - interaction plots (H3)
# --------------------------------------------------------------------------- #
def figure_interaction(result: AblationResult, outdir: str) -> List[str]:
    """Figure 5: V x G interaction. Non-parallel lines are the interaction."""

    _apply_style()
    seed = result.config.seed

    specs = [
        ("latency_ms", "Latency (ms)", "modelled milliseconds"),
        ("tokens", "Token consumption", "tokens"),
        ("correct", "Hypothesis accuracy", "proportion correct"),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(10.5, 3.5))

    for ax, (attribute, title, ylabel) in zip(axes, specs):
        _despine(ax)
        data = align(result, attribute)
        for validation, colour, marker, label in (
            (0, HUE_V0, "o", "Validation off"),
            (1, HUE_V1, "s", "Validation on"),
        ):
            cells = ("Baseline", "G-only") if validation == 0 else ("V-only", "Full")
            means, errs = [], [[], []]
            for cell in cells:
                value, lo, hi = _ci_for(data[cell], seed)
                means.append(value)
                errs[0].append(lo)
                errs[1].append(hi)
            ax.errorbar([0, 1], means, yerr=errs, color=colour, marker=marker,
                        markersize=7, linewidth=2.0, capsize=3.5,
                        markeredgecolor="white", markeredgewidth=1.2, label=label)
            ax.annotate(label, xy=(1, means[1]), xytext=(4, 0),
                        textcoords="offset points", fontsize=7.4, color=colour,
                        va="center")

        ax.set_xticks([0, 1])
        ax.set_xticklabels(["Governance off", "Governance on"])
        ax.set_xlim(-0.25, 1.55)
        ax.set_ylabel(ylabel)
        ax.set_title(title)

    fig.suptitle("Figure 5  H3: the two mechanisms do not combine additively — "
                 "non-parallel traces indicate interaction",
                 fontsize=10, fontweight="bold", color=INK_PRIMARY, y=1.04)
    fig.tight_layout()
    return _save(fig, outdir, "fig05_interaction")


# --------------------------------------------------------------------------- #
# Figure 6 - calibration
# --------------------------------------------------------------------------- #
def figure_calibration(result: AblationResult, outdir: str) -> List[str]:
    """Figure 6: reliability diagram and Brier decomposition."""

    _apply_style()
    acc = align(result, "correct")
    conf = align(result, "confidence")

    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(9.5, 4.0))
    _despine(ax)

    ax.plot([0, 1], [0, 1], color=INK_MUTED, linewidth=1.0, linestyle="--",
            label="perfect calibration", zorder=1)

    decomps = {}
    for cell in PLOT_ORDER:
        decomp = brier_decomposition(conf[cell], [int(x) for x in acc[cell]])
        decomps[cell] = decomp
        face, _ = CELL_STYLE[cell]
        xs = [c for c, n in zip(decomp.bin_confidence, decomp.bin_counts) if n]
        ys = [o for o, n in zip(decomp.bin_outcome, decomp.bin_counts) if n]
        marker = "o" if cell in ("Baseline", "V-only") else "s"
        ax.plot(xs, ys, marker=marker, markersize=8, linewidth=1.8, color=face,
                markeredgecolor="white", markeredgewidth=1.3, label=cell, zorder=3)

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("stated confidence")
    ax.set_ylabel("observed frequency correct")
    ax.set_title("Reliability diagram")
    ax.legend(loc="upper left")

    # Brier decomposition: reliability (lower better) vs resolution (higher better).
    _despine(ax2)
    width = 0.26
    terms = ("reliability", "resolution", "uncertainty")
    for i, cell in enumerate(PLOT_ORDER):
        face, hatch = CELL_STYLE[cell]
        values = [getattr(decomps[cell], t) for t in terms]
        xs = [j + (i - 1.5) * width for j in range(len(terms))]
        ax2.bar(xs, values, width=width * 0.88, color=face, hatch=hatch,
                edgecolor="white", linewidth=1.0)
    ax2.set_xticks(range(len(terms)))
    ax2.set_xticklabels(["Reliability\n(lower better)", "Resolution\n(higher better)",
                         "Uncertainty\n(base rate)"])
    ax2.set_ylabel("contribution to Brier score")
    ax2.set_title("Murphy decomposition")

    fig.suptitle("Figure 6  Calibration: Brier score decomposed into reliability, "
                 "resolution and irreducible uncertainty",
                 fontsize=10, fontweight="bold", color=INK_PRIMARY, y=1.03)
    _factorial_legend(fig)
    fig.tight_layout()
    return _save(fig, outdir, "fig06_calibration")


# --------------------------------------------------------------------------- #
# Figure 7 - alpha sensitivity
# --------------------------------------------------------------------------- #
def figure_alpha_sensitivity(result: AblationResult, outdir: str) -> List[str]:
    """Figure 7: robustness of the band assignment to the ST weighting."""

    _apply_style()
    cfg = result.config
    sweep = test_h4(result).extras["alpha_sensitivity"]
    alphas = sorted(float(k.split("=")[1]) for k in sweep)

    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    _despine(ax)

    lo, hi = -2.0, 2.0
    ax.axhspan(lo, cfg.st_band_low, color=BAND_COLOURS["full-governance"], zorder=0)
    ax.axhspan(cfg.st_band_low, cfg.st_band_high,
               color=BAND_COLOURS["adaptive-governance"], zorder=0)
    ax.axhspan(cfg.st_band_high, hi, color=BAND_COLOURS["minimal-governance"], zorder=0)

    for cell in PLOT_ORDER:
        face, _ = CELL_STYLE[cell]
        marker = "o" if cell in ("Baseline", "V-only") else "s"
        ys = [sweep[f"alpha={a:g}"][cell]["median_st"] for a in alphas]
        ax.plot(alphas, ys, marker=marker, markersize=7, linewidth=2.0,
                color=face, markeredgecolor="white", markeredgewidth=1.2,
                label=cell, zorder=3)
        ax.annotate(cell, xy=(alphas[-1], ys[-1]), xytext=(5, 0),
                    textcoords="offset points", fontsize=7.6, color=face,
                    va="center", fontweight="bold")

    ax.axvline(cfg.st_alpha, color=INK_PRIMARY, linewidth=1.0, linestyle=":")
    ax.text(cfg.st_alpha, hi * 0.94, "  pre-registered α = 0.5", fontsize=7.4,
            color=INK_PRIMARY, va="top")

    ax.set_xlabel("α  (weight on latency; β = 1 − α weights tokens)")
    ax.set_ylabel("median Security Tax")
    ax.set_xlim(-0.03, 1.22)
    ax.set_ylim(lo, hi)
    ax.set_title("Figure 7  H4 robustness: band assignment under reweighting",
                 fontsize=10)
    fig.tight_layout()
    return _save(fig, outdir, "fig07_alpha_sensitivity")


# --------------------------------------------------------------------------- #
# Figure 8 - measured governance cost
# --------------------------------------------------------------------------- #
def figure_governance_breakdown(result: AblationResult, outdir: str) -> List[str]:
    """Figure 8: measured wall-clock cost of governance, by component.

    These are the campaign's genuinely *measured* latencies -- real elapsed time
    through real HMAC verification, SHA-256 chaining, entity redaction and queue
    bookkeeping -- as distinct from the modelled inference and deployment costs
    that dominate Figure 3.

    The per-component bars come from a single campaign and should be read as
    indicative only: repeated campaigns show the end-to-end total stable to
    ~1.45x but individual components swinging by up to 3.6x, with no stable
    ranking between them (Limitation L9). The figure is annotated accordingly
    rather than left to imply a precision the measurement does not have.
    """

    _apply_style()
    governed = [o for o in result.observations
                if o.governance == 1 and o.governed_events > 0]
    if not governed:
        return []

    events = sum(o.governed_events for o in governed)
    components = [
        ("Policy evaluation\nfG(e) + HMAC", sum(o.measured_policy_ms for o in governed)),
        ("Audit chain\nSHA-256 append", sum(o.measured_audit_ms for o in governed)),
        ("Entity redaction\nneed-to-know", sum(o.measured_redaction_ms for o in governed)),
        ("Mediation queue\nbookkeeping", sum(o.measured_queue_ms for o in governed)),
    ]
    labels = [c[0] for c in components]
    per_event_us = [c[1] * 1000.0 / events for c in components]

    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(10.0, 3.9))
    _despine(ax)

    bars = ax.barh(range(len(labels)), per_event_us, height=0.6,
                   color=HUE_ACCENT, edgecolor="white", linewidth=1.4)
    for i, value in enumerate(per_event_us):
        ax.text(value, i, f"  {value:.2f} µs", va="center", ha="left",
                fontsize=7.6, color=INK_PRIMARY)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=7.6)
    ax.invert_yaxis()
    ax.set_xlabel("measured µs per mediated event")
    ax.set_xlim(0, max(per_event_us) * 1.32)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", visible=True)
    ax.set_title(f"Per-event cost  (n = {events:,} mediated events)")

    # Distribution of measured per-observation governance time.
    _despine(ax2)
    for cell, offset in (("G-only", 0), ("Full", 1)):
        values = [o.measured_governance_ms for o in result.observations
                  if o.cell == cell and o.measured_governance_ms > 0]
        if not values:
            continue
        face, hatch = CELL_STYLE[cell]
        parts = ax2.violinplot([values], positions=[offset], widths=0.6,
                               showextrema=False)
        for body in parts["bodies"]:
            body.set_facecolor(face)
            body.set_edgecolor("white")
            body.set_alpha(0.85)
            if hatch:
                body.set_hatch(hatch)
        ax2.scatter([offset], [_median(values)], color=INK_PRIMARY, s=22,
                    zorder=4, marker="_", linewidths=1.6)
        ax2.text(offset, _median(values), f"  Mdn {_median(values):.3f} ms",
                 fontsize=7.4, color=INK_PRIMARY, va="center", ha="left")

    ax2.set_xticks([0, 1])
    ax2.set_xticklabels(["G-only", "Full GMAIS"])
    ax2.set_xlim(-0.6, 1.9)
    ax2.set_ylabel("measured ms per observation")
    ax2.set_title("Governance wall clock per observation")

    # A handful of observations catch a scheduler preemption and land orders of
    # magnitude high. Left unclipped they flatten every distribution into a line,
    # so the view is clipped at the 99th percentile and the exclusion is stated
    # on the axis rather than passed off silently.
    governed_ms = [o.measured_governance_ms for o in result.observations
                   if o.measured_governance_ms > 0]
    if governed_ms:
        ceiling = _quantile(governed_ms, 0.99) * 1.25
        hidden = sum(1 for v in governed_ms if v > ceiling)
        ax2.set_ylim(0, ceiling)
        if hidden:
            ax2.set_xlabel(f"view clipped at the 99th percentile "
                           f"({hidden} of {len(governed_ms)} observations above)",
                           fontsize=7, color=INK_MUTED)

    resolution = result.environment.get("clock_resolution_ns")
    footnote = ("Single campaign, warm-up observations discarded. Measured with "
                "time.perf_counter_ns"
                + (f"; clock resolution {resolution:.0f} ns" if resolution else "")
                + f" on {result.environment.get('platform', 'the campaign host')}.")
    caveat = ("Component attribution is not stable between runs — see "
              "`gmais.cli timing --repeats N` and Limitation L9. The end-to-end "
              "total is stable to ~1.45×; the per-component split is not.")
    fig.text(0.5, -0.06, footnote, ha="center", fontsize=7, color=INK_MUTED)
    fig.text(0.5, -0.115, caveat, ha="center", fontsize=7, color=INK_MUTED)

    fig.suptitle("Figure 8  Measured governance overhead, attributed by component",
                 fontsize=10, fontweight="bold", color=INK_PRIMARY, y=1.04)
    fig.tight_layout()
    return _save(fig, outdir, "fig08_governance_breakdown")


# --------------------------------------------------------------------------- #
# Figure 9 - Security Tax by complexity tier
# --------------------------------------------------------------------------- #
def figure_tax_by_tier(result: AblationResult, outdir: str) -> List[str]:
    """Figure 9: does the Security Tax scale with analytical complexity?"""

    _apply_style()
    tiers = ["low", "medium", "high"]
    by_tier_cell: Dict[str, Dict[str, List[float]]] = {t: {} for t in tiers}
    for st in result.security_tax:
        by_tier_cell[st.tier].setdefault(st.cell, []).append(st.security_tax)

    fig, ax = plt.subplots(figsize=(7.6, 4.0))
    _despine(ax)

    width = 0.2
    for i, cell in enumerate(PLOT_ORDER):
        face, hatch = CELL_STYLE[cell]
        medians = [_median(by_tier_cell[t].get(cell, [])) for t in tiers]
        q1 = [_quantile(by_tier_cell[t].get(cell, []), 0.25) for t in tiers]
        q3 = [_quantile(by_tier_cell[t].get(cell, []), 0.75) for t in tiers]
        xs = [j + (i - 1.5) * width for j in range(len(tiers))]
        ax.bar(xs, medians, width=width * 0.88, color=face, hatch=hatch,
               edgecolor="white", linewidth=1.2)
        ax.errorbar(xs, medians,
                    yerr=[[m - a for m, a in zip(medians, q1)],
                          [b - m for m, b in zip(medians, q3)]],
                    fmt="none", ecolor=INK_PRIMARY, elinewidth=1.0, capsize=3)

    ax.axhline(0, color=INK_MUTED, linewidth=0.9)
    ax.set_xticks(range(len(tiers)))
    ax.set_xticklabels([f"{t.capitalize()} complexity" for t in tiers])
    ax.set_ylabel("median Security Tax (bars: IQR)")
    ax.set_title("Figure 9  Security Tax across complexity tiers", fontsize=10)
    _factorial_legend(fig)
    fig.tight_layout()
    return _save(fig, outdir, "fig09_tax_by_tier")


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #
def render_all(result: AblationResult, outdir: str) -> List[str]:
    """Render every figure in the results package."""

    paths: List[str] = []
    paths += figure_architecture(outdir)
    paths += figure_ablation_performance(result, outdir)
    paths += figure_overhead(result, outdir)
    paths += figure_security_tax(result, outdir)
    paths += figure_interaction(result, outdir)
    paths += figure_calibration(result, outdir)
    paths += figure_alpha_sensitivity(result, outdir)
    paths += figure_governance_breakdown(result, outdir)
    paths += figure_tax_by_tier(result, outdir)
    return paths
