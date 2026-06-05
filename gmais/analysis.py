"""Inference and policy-threshold derivation (Sections 3.3.6 / 3.3.7).

Takes an :class:`~gmais.ablation.AblationResult` and produces:

* per-cell / per-tier Security-Tax summaries and policy-band assignments,
* point estimates of the four factorial quantities mapping to H1-H4, and
* optional non-parametric triangulation (Friedman + Wilcoxon, Holm-Bonferroni)
  when scipy is available.

The full thesis programme is Bayesian hierarchical with a log-normal likelihood;
that requires a PPL (Stan/PyMC) and the 540-observation campaign. What is
implemented here is the descriptive and non-parametric layer that the thesis
specifies as triangulation (Section 3.3.6) plus the policy-band mapping
(Section 3.3.7), which together run with no heavyweight dependencies.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List

from .ablation import AblationResult
from .config import BASELINE_CELL


def _mean(xs: List[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _median(xs: List[float]) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0


@dataclass
class FactorialEffects:
    """Point estimates aligned with H1-H3 (descriptive, not the Bayesian fit)."""

    validation_accuracy_effect: float  # H1
    governance_latency_effect_ms: float  # H2 (latency)
    governance_token_effect: float  # H2 (tokens)
    interaction_latency_ms: float  # H3 (latency)
    interaction_tokens: float  # H3 (tokens)


def _cell_means(result: AblationResult) -> Dict[str, Dict[str, float]]:
    cells: Dict[str, Dict[str, list]] = {}
    for o in result.observations:
        c = cells.setdefault(o.cell, {"acc": [], "lat": [], "tok": []})
        c["acc"].append(o.correct)
        c["lat"].append(o.latency_ms)
        c["tok"].append(o.tokens)
    return {k: {m: _mean(v) for m, v in d.items()} for k, d in cells.items()}


def factorial_effects(result: AblationResult) -> FactorialEffects:
    m = _cell_means(result)
    base, v, g, full = m["Baseline"], m["V-only"], m["G-only"], m["Full"]

    # H1: validation main effect on accuracy, averaged over governance.
    val_acc = 0.5 * ((v["acc"] - base["acc"]) + (full["acc"] - g["acc"]))
    # H2: governance main effect on latency/tokens, averaged over validation.
    gov_lat = 0.5 * ((g["lat"] - base["lat"]) + (full["lat"] - v["lat"]))
    gov_tok = 0.5 * ((g["tok"] - base["tok"]) + (full["tok"] - v["tok"]))
    # H3: interaction = (Full - V) - (G - Baseline).
    inter_lat = (full["lat"] - v["lat"]) - (g["lat"] - base["lat"])
    inter_tok = (full["tok"] - v["tok"]) - (g["tok"] - base["tok"])

    return FactorialEffects(
        validation_accuracy_effect=round(val_acc, 4),
        governance_latency_effect_ms=round(gov_lat, 3),
        governance_token_effect=round(gov_tok, 2),
        interaction_latency_ms=round(inter_lat, 3),
        interaction_tokens=round(inter_tok, 2),
    )


def security_tax_summary(result: AblationResult) -> Dict[str, dict]:
    """Per-cell Security-Tax distribution and policy-band assignment."""

    by_cell: Dict[str, List[float]] = {}
    bands_by_cell: Dict[str, Dict[str, int]] = {}
    for st in result.security_tax:
        by_cell.setdefault(st.cell, []).append(st.security_tax)
        b = bands_by_cell.setdefault(st.cell, {})
        b[st.band] = b.get(st.band, 0) + 1

    summary: Dict[str, dict] = {}
    for cell, vals in by_cell.items():
        summary[cell] = {
            "n": len(vals),
            "mean_st": round(_mean(vals), 4),
            "median_st": round(_median(vals), 4),
            "min_st": round(min(vals), 4),
            "max_st": round(max(vals), 4),
            "bands": bands_by_cell[cell],
        }
    return summary


def policy_recommendation(result: AblationResult) -> Dict[str, str]:
    """Map each non-baseline cell's median ST to a policy regime (Section 3.3.7)."""

    cfg = result.config
    recs: Dict[str, str] = {}
    summary = security_tax_summary(result)
    for cell, s in summary.items():
        if cell == BASELINE_CELL.name:
            continue
        median = s["median_st"]
        if median < cfg.st_band_low:
            recs[cell] = "Full governance deployment (ST < 0.5)"
        elif median > cfg.st_band_high:
            recs[cell] = "Minimal governance (ST > 1.5)"
        else:
            recs[cell] = "Adaptive governance (0.5 <= ST <= 1.5)"
    return recs


def nonparametric_triangulation(result: AblationResult) -> Dict[str, object]:
    """Friedman + Wilcoxon (Holm-Bonferroni) on latency, if scipy is present."""

    try:
        from itertools import combinations

        from scipy import stats  # type: ignore
    except Exception:  # pragma: no cover - scipy optional
        return {"available": False, "reason": "scipy not installed"}

    # Build per-scenario latency vectors aligned across the four cells.
    cells = ["Baseline", "V-only", "G-only", "Full"]
    by_key: Dict[str, Dict[str, float]] = {}
    for o in result.observations:
        by_key.setdefault(o.scenario_id, {})[o.cell] = o.latency_ms
    aligned = [v for v in by_key.values() if all(c in v for c in cells)]
    if len(aligned) < 3:
        return {"available": False, "reason": "insufficient aligned observations"}

    columns = {c: [row[c] for row in aligned] for c in cells}
    friedman_stat, friedman_p = stats.friedmanchisquare(*[columns[c] for c in cells])

    # Pairwise Wilcoxon with Holm-Bonferroni correction.
    pairs = list(combinations(cells, 2))
    raw = []
    for a, b in pairs:
        try:
            _, p = stats.wilcoxon(columns[a], columns[b])
        except ValueError:
            p = 1.0
        raw.append(((a, b), p))
    raw.sort(key=lambda kv: kv[1])
    m = len(raw)
    corrected = {}
    for i, ((a, b), p) in enumerate(raw):
        corrected[f"{a} vs {b}"] = round(min(1.0, p * (m - i)), 6)

    return {
        "available": True,
        "friedman_chi2": round(float(friedman_stat), 4),
        "friedman_p": round(float(friedman_p), 6),
        "wilcoxon_holm_bonferroni": corrected,
        "n_aligned": len(aligned),
    }


def build_report(result: AblationResult) -> str:
    """Render a human-readable summary of the ablation campaign."""

    cfg = result.config
    effects = factorial_effects(result)
    st_summary = security_tax_summary(result)
    recs = policy_recommendation(result)
    nonpar = nonparametric_triangulation(result)

    lines: List[str] = []
    lines.append("=" * 70)
    lines.append("GMAIS 2x2 FACTORIAL ABLATION REPORT")
    lines.append("=" * 70)
    lines.append(f"Backend: {cfg.backend}    Seed: {cfg.seed}    "
                 f"Observations: {len(result.observations)} "
                 f"(target {cfg.total_observations})")
    lines.append("")

    lines.append("PER-CELL PERFORMANCE")
    lines.append("-" * 70)
    header = f"{'Cell':<10}{'N':>5}{'Acc':>8}{'Brier':>8}{'Det-F1':>9}{'Lat(ms)':>11}{'Tokens':>9}"
    lines.append(header)
    for cell in ["Baseline", "V-only", "G-only", "Full"]:
        m = result.per_cell_metrics[cell]
        lines.append(
            f"{cell:<10}{m['n']:>5}{m['hypothesis_accuracy']:>8.3f}"
            f"{m['brier_score']:>8.3f}{m['detection']['f1']:>9.3f}"
            f"{m['mean_latency_ms']:>11.1f}{m['mean_tokens']:>9.1f}"
        )
    lines.append("")

    lines.append("FACTORIAL EFFECTS (descriptive point estimates)")
    lines.append("-" * 70)
    lines.append(f"  H1  Validation -> accuracy        : {effects.validation_accuracy_effect:+.4f}")
    lines.append(f"  H2  Governance -> latency (ms)     : {effects.governance_latency_effect_ms:+.2f}")
    lines.append(f"  H2  Governance -> tokens           : {effects.governance_token_effect:+.2f}")
    lines.append(f"  H3  V x G interaction (latency ms) : {effects.interaction_latency_ms:+.2f}")
    lines.append(f"  H3  V x G interaction (tokens)     : {effects.interaction_tokens:+.2f}")
    lines.append("")

    lines.append("SECURITY TAX DISTRIBUTION  (ST = a*z(dL) + b*z(dC))")
    lines.append("-" * 70)
    lines.append(f"{'Cell':<10}{'N':>5}{'mean':>9}{'median':>9}{'min':>9}{'max':>9}")
    for cell in ["Baseline", "V-only", "G-only", "Full"]:
        s = st_summary.get(cell)
        if s:
            lines.append(
                f"{cell:<10}{s['n']:>5}{s['mean_st']:>9.3f}{s['median_st']:>9.3f}"
                f"{s['min_st']:>9.3f}{s['max_st']:>9.3f}"
            )
    lines.append("")

    lines.append("POLICY-THRESHOLD RECOMMENDATION (H4)")
    lines.append("-" * 70)
    for cell, rec in recs.items():
        lines.append(f"  {cell:<10}: {rec}")
    lines.append("")

    lines.append("NON-PARAMETRIC TRIANGULATION")
    lines.append("-" * 70)
    if nonpar.get("available"):
        lines.append(f"  Friedman chi2={nonpar['friedman_chi2']} "
                     f"p={nonpar['friedman_p']} (n={nonpar['n_aligned']})")
        for pair, p in nonpar["wilcoxon_holm_bonferroni"].items():
            lines.append(f"    Wilcoxon {pair:<22}: p_adj={p}")
    else:
        lines.append(f"  unavailable: {nonpar.get('reason')}")
    lines.append("")

    # Audit-integrity attestation across governed cells.
    audit_failures = sum(
        m["audit_failures"] for m in result.per_cell_metrics.values()
    )
    lines.append(f"AUDIT-CHAIN INTEGRITY: "
                 f"{'INTACT across all governed observations' if audit_failures == 0 else f'{audit_failures} FAILURES'}")
    lines.append("=" * 70)
    return "\n".join(lines)
