"""Confirmatory tests of H1-H4 over the observation matrix (Section 3.3.6).

This module turns the campaign's observation matrix into the statistical
results the thesis's four hypotheses are stated in terms of. It reports, for
every hypothesis, a test, an effect size and an interval -- not a point estimate
alone, and not a p-value alone.

The confirmatory family
-----------------------
Six tests are pre-registered as confirmatory and carry Holm-Bonferroni adjusted
p-values across the family:

1. H1 at G=0: does validation raise accuracy without governance?
2. H1 at G=1: does validation raise accuracy under governance?
3. H2 at V=0: does governance raise latency without validation?
4. H2 at V=1: does governance raise latency under validation?
5. H2 tokens: does governance raise token consumption?
6. H3: is the V x G interaction on latency non-zero?

Everything else reported here -- detection metrics, Brier decompositions, the
accuracy interaction, band proportions, the alpha sweep -- is exploratory and
is labelled as such, so a reader can see which claims the multiplicity
correction covers and which it does not.

Testing each main effect **at both levels of the other factor** rather than
collapsing to a marginal effect is deliberate. In a 2x2 design a marginal main
effect is only interpretable when the interaction is negligible, and H3 exists
precisely because the thesis does not assume that.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .ablation import AblationResult
from .metrics import compute_security_tax
from .stats import (
    CELL_ORDER,
    BrierDecomposition,
    Interval,
    PairedTest,
    bootstrap_ci,
    brier_decomposition,
    cliffs_delta,
    holm_bonferroni,
    mcnemar_exact,
    wilcoxon_paired,
    wilson_ci,
    _mean,
    _median,
)


# --------------------------------------------------------------------------- #
# Aligning the matrix into within-scenario vectors
# --------------------------------------------------------------------------- #
def align(result: AblationResult, attribute: str) -> Dict[str, List[float]]:
    """Return one vector per cell, aligned position-by-position by scenario.

    Scenarios missing an observation in any cell are dropped entirely rather
    than partially included, so index *i* refers to the same scenario in every
    returned vector and the paired tests stay valid.
    """

    by_scenario: Dict[str, Dict[str, float]] = {}
    for obs in result.observations:
        by_scenario.setdefault(obs.scenario_id, {})[obs.cell] = float(
            getattr(obs, attribute)
        )

    complete = [
        sid for sid, cells in by_scenario.items()
        if all(cell in cells for cell in CELL_ORDER)
    ]
    complete.sort()
    return {
        cell: [by_scenario[sid][cell] for sid in complete] for cell in CELL_ORDER
    }


def scenario_ids(result: AblationResult) -> List[str]:
    """Scenario ids in the order :func:`align` produces its vectors."""

    by_scenario: Dict[str, set] = {}
    for obs in result.observations:
        by_scenario.setdefault(obs.scenario_id, set()).add(obs.cell)
    return sorted(
        sid for sid, cells in by_scenario.items()
        if all(cell in cells for cell in CELL_ORDER)
    )


def tiers_by_scenario(result: AblationResult) -> Dict[str, str]:
    return {obs.scenario_id: obs.tier for obs in result.observations}


# --------------------------------------------------------------------------- #
# H1 - Validation and analytical accuracy
# --------------------------------------------------------------------------- #
@dataclass
class HypothesisResult:
    """A hypothesis, the tests that bear on it, and the verdict."""

    hypothesis: str
    statement: str
    tests: List[PairedTest] = field(default_factory=list)
    intervals: Dict[str, Interval] = field(default_factory=dict)
    extras: Dict[str, object] = field(default_factory=dict)
    verdict: str = ""

    def as_dict(self) -> Dict[str, object]:
        return {
            "hypothesis": self.hypothesis,
            "statement": self.statement,
            "verdict": self.verdict,
            "tests": [t.as_dict() for t in self.tests],
            "intervals": {k: v.as_dict() for k, v in self.intervals.items()},
            "extras": self.extras,
        }


def test_h1(result: AblationResult) -> HypothesisResult:
    """H1: the Validator raises analytical accuracy."""

    seed = result.config.seed
    acc = align(result, "correct")

    t_no_gov = mcnemar_exact(
        acc["Baseline"], acc["V-only"], name="H1 | G=0: Baseline -> V-only"
    )
    t_gov = mcnemar_exact(
        acc["G-only"], acc["Full"], name="H1 | G=1: G-only -> Full"
    )

    # Main effect: the per-scenario average of the two simple effects. Bootstrap
    # over scenarios, which is the unit of independence.
    simple = [
        0.5 * ((v - b) + (f - g))
        for b, v, g, f in zip(acc["Baseline"], acc["V-only"], acc["G-only"], acc["Full"])
    ]
    main_effect = bootstrap_ci(simple, _mean, seed=seed)

    # Detection quality, pooled at the claim level across the corpus.
    detection = {
        cell: result.per_cell_metrics[cell]["detection"] for cell in CELL_ORDER
    }

    # Calibration: Brier and its decomposition, per cell.
    conf = align(result, "confidence")
    briers = {
        cell: brier_decomposition(conf[cell], [int(x) for x in acc[cell]])
        for cell in CELL_ORDER
    }

    # Rubric composite: the graded, non-binary GTKG score (Section 3.2.1).
    rubric = align(result, "rubric_composite")
    rubric_test = wilcoxon_paired(
        rubric["Baseline"], rubric["V-only"],
        name="H1 (exploratory): rubric composite, Baseline -> V-only", seed=seed,
    )

    verdict = (
        "SUPPORTED" if (t_no_gov.p_value < 0.05 and t_gov.p_value < 0.05
                        and main_effect.low > 0)
        else "NOT SUPPORTED"
    )

    return HypothesisResult(
        hypothesis="H1",
        statement=("Embedding structured validation (Admiralty grading + ACH under "
                   "bounded-rationality control) raises analytical accuracy relative "
                   "to an unvalidated multi-agent baseline."),
        tests=[t_no_gov, t_gov, rubric_test],
        intervals={"validation_main_effect_accuracy": main_effect},
        extras={
            "cell_accuracy": {c: round(_mean(acc[c]), 4) for c in CELL_ORDER},
            "detection": detection,
            "brier": {c: briers[c].as_dict() for c in CELL_ORDER},
            "brier_bins": {
                c: {
                    "counts": briers[c].bin_counts,
                    "confidence": briers[c].bin_confidence,
                    "observed": briers[c].bin_outcome,
                }
                for c in CELL_ORDER
            },
            "rubric_composite_mean": {c: round(_mean(rubric[c]), 4) for c in CELL_ORDER},
        },
        verdict=verdict,
    )


# --------------------------------------------------------------------------- #
# H2 - Governance overhead
# --------------------------------------------------------------------------- #
def test_h2(result: AblationResult) -> HypothesisResult:
    """H2: the Governance Layer imposes measurable latency and token overhead."""

    seed = result.config.seed
    lat = align(result, "latency_ms")
    tok = align(result, "tokens")
    measured = align(result, "measured_governance_ms")

    t_lat_v0 = wilcoxon_paired(
        lat["Baseline"], lat["G-only"],
        name="H2 | V=0: latency, Baseline -> G-only", seed=seed,
    )
    t_lat_v1 = wilcoxon_paired(
        lat["V-only"], lat["Full"],
        name="H2 | V=1: latency, V-only -> Full", seed=seed,
    )
    t_tok = wilcoxon_paired(
        [0.5 * (b + v) for b, v in zip(tok["Baseline"], tok["V-only"])],
        [0.5 * (g + f) for g, f in zip(tok["G-only"], tok["Full"])],
        name="H2: token consumption, ungoverned -> governed", seed=seed,
    )

    lat_main = bootstrap_ci(
        [0.5 * ((g - b) + (f - v))
         for b, v, g, f in zip(lat["Baseline"], lat["V-only"], lat["G-only"], lat["Full"])],
        _mean, seed=seed,
    )
    tok_main = bootstrap_ci(
        [0.5 * ((g - b) + (f - v))
         for b, v, g, f in zip(tok["Baseline"], tok["V-only"], tok["G-only"], tok["Full"])],
        _mean, seed=seed,
    )

    # Relative overhead, which is what a deployment decision actually turns on.
    rel_lat = bootstrap_ci(
        [((g - b) / b) for b, g in zip(lat["Baseline"], lat["G-only"]) if b > 0],
        _mean, seed=seed,
    )
    rel_tok = bootstrap_ci(
        [((g - b) / b) for b, g in zip(tok["Baseline"], tok["G-only"]) if b > 0],
        _mean, seed=seed,
    )

    # Measured wall clock of the mediation actually executed.
    measured_ci = bootstrap_ci(
        [x for x in measured["Full"] if x > 0], _mean, seed=seed
    )
    per_event = _per_event_measured(result)

    verdict = (
        "SUPPORTED" if (t_lat_v0.p_value < 0.05 and t_lat_v1.p_value < 0.05
                        and lat_main.low > 0 and tok_main.low > 0)
        else "NOT SUPPORTED"
    )

    return HypothesisResult(
        hypothesis="H2",
        statement=("Governance mediation (authenticated delegation, need-to-know "
                   "enforcement, hash-chained audit) imposes a measurable and "
                   "quantifiable latency and token overhead."),
        tests=[t_lat_v0, t_lat_v1, t_tok],
        intervals={
            "governance_main_effect_latency_ms": lat_main,
            "governance_main_effect_tokens": tok_main,
            "governance_relative_latency": rel_lat,
            "governance_relative_tokens": rel_tok,
            "measured_governance_ms_full_cell": measured_ci,
        },
        extras={
            "cell_latency_ms": {c: round(_mean(lat[c]), 3) for c in CELL_ORDER},
            "cell_tokens": {c: round(_mean(tok[c]), 2) for c in CELL_ORDER},
            "cell_measured_governance_ms": {
                c: round(_mean(measured[c]), 5) for c in CELL_ORDER
            },
            "measured_per_event_us": per_event,
            "cliffs_delta_latency_V0": round(
                cliffs_delta(lat["Baseline"], lat["G-only"]), 4
            ),
        },
        verdict=verdict,
    )


def _per_event_measured(result: AblationResult) -> Dict[str, float]:
    """Mean measured microseconds per mediated event, by governance component.

    The first ``timing_warmup_observations`` governed observations are discarded.
    Early observations carry interpreter warm-up, cold instruction and data
    caches and first-touch allocation, all of which inflate a microsecond-scale
    measurement; including them biases the mean upward and, worse, biases it
    unevenly across components depending on which runs first.
    """

    governed = [o for o in result.observations
                if o.governance == 1 and o.governed_events > 0]
    warmup = max(0, int(getattr(result.config, "timing_warmup_observations", 0)))
    if len(governed) > warmup:
        governed = governed[warmup:]
    if not governed:
        return {}
    events = sum(o.governed_events for o in governed)
    return {
        "n_mediated_events": events,
        "warmup_observations_discarded": warmup,
        "policy_eval_us": round(
            sum(o.measured_policy_ms for o in governed) * 1000 / events, 3),
        "audit_record_us": round(
            sum(o.measured_audit_ms for o in governed) * 1000 / events, 3),
        "redaction_us": round(
            sum(o.measured_redaction_ms for o in governed) * 1000 / events, 3),
        "queue_us": round(
            sum(o.measured_queue_ms for o in governed) * 1000 / events, 3),
        "governance_total_us": round(
            sum(o.measured_governance_ms for o in governed) * 1000 / events, 3),
    }


# --------------------------------------------------------------------------- #
# H3 - Interaction
# --------------------------------------------------------------------------- #
def test_h3(result: AblationResult) -> HypothesisResult:
    """H3: validation and governance interact rather than combining additively.

    The interaction contrast is formed **within each scenario** --
    ``(Full - V-only) - (G-only - Baseline)`` -- giving one value per scenario,
    which is then tested against zero. This is the correct paired analysis for a
    repeated-measures 2x2 and needs no distributional assumption beyond symmetry.
    """

    seed = result.config.seed
    out: Dict[str, PairedTest] = {}
    intervals: Dict[str, Interval] = {}
    contrasts: Dict[str, List[float]] = {}

    for attribute, label in (("latency_ms", "latency (ms)"),
                             ("tokens", "tokens"),
                             ("correct", "accuracy")):
        v = align(result, attribute)
        contrast = [
            (f - vo) - (g - b)
            for b, vo, g, f in zip(v["Baseline"], v["V-only"], v["G-only"], v["Full"])
        ]
        contrasts[attribute] = contrast
        zeros = [0.0] * len(contrast)
        test = wilcoxon_paired(
            zeros, contrast, name=f"H3: V x G interaction on {label}", seed=seed
        )
        out[attribute] = test
        intervals[f"interaction_{attribute}"] = bootstrap_ci(contrast, _mean, seed=seed)

    lat_test = out["latency_ms"]
    verdict = "SUPPORTED" if lat_test.p_value < 0.05 else "NOT SUPPORTED"

    return HypothesisResult(
        hypothesis="H3",
        statement=("Validation and governance interact: their joint cost and joint "
                   "benefit are not the sum of their separate contributions."),
        tests=[out["latency_ms"], out["tokens"], out["correct"]],
        intervals=intervals,
        extras={
            "interaction_sign": {
                k: ("super-additive" if _mean(v) > 0
                    else "sub-additive" if _mean(v) < 0 else "additive")
                for k, v in contrasts.items()
            },
            "note": ("The accuracy interaction is exploratory: it is driven by the "
                     "bias-control pathway, where governance can only help in cells "
                     "that lack a Validator to absorb the same error."),
        },
        verdict=verdict,
    )


# --------------------------------------------------------------------------- #
# H4 - Security Tax and policy bands
# --------------------------------------------------------------------------- #
def test_h4(result: AblationResult) -> HypothesisResult:
    """H4: the Security Tax partitions configurations into policy bands."""

    cfg = result.config
    seed = cfg.seed

    by_cell: Dict[str, List[float]] = {}
    bands_by_cell: Dict[str, Dict[str, int]] = {}
    by_tier: Dict[str, Dict[str, List[float]]] = {}
    for st in result.security_tax:
        by_cell.setdefault(st.cell, []).append(st.security_tax)
        bands_by_cell.setdefault(st.cell, {})
        bands_by_cell[st.cell][st.band] = bands_by_cell[st.cell].get(st.band, 0) + 1
        by_tier.setdefault(st.tier, {}).setdefault(st.cell, []).append(st.security_tax)

    distribution: Dict[str, object] = {}
    intervals: Dict[str, Interval] = {}
    for cell in CELL_ORDER:
        values = by_cell.get(cell, [])
        if not values:
            continue
        intervals[f"median_st_{cell}"] = bootstrap_ci(values, _median, seed=seed)
        n = len(values)
        band_props = {
            band: wilson_ci(bands_by_cell[cell].get(band, 0), n).as_dict()
            for band in ("full-governance", "adaptive-governance", "minimal-governance")
        }
        distribution[cell] = {
            "n": n,
            "mean": round(_mean(values), 4),
            "median": round(_median(values), 4),
            "sd": round(_sd(values), 4),
            "iqr": [round(_q(values, 0.25), 4), round(_q(values, 0.75), 4)],
            "min": round(min(values), 4),
            "max": round(max(values), 4),
            "band_counts": bands_by_cell[cell],
            "band_proportions": band_props,
        }

    # Does the Full cell's Security Tax exceed the G-only cell's? That is the
    # substantive H4 question: whether adding validation on top of governance
    # pushes a configuration across a band boundary.
    full_vs_g = wilcoxon_paired(
        _st_vector(result, "G-only"), _st_vector(result, "Full"),
        name="H4 (exploratory): Security Tax, G-only -> Full", seed=seed,
    )

    return HypothesisResult(
        hypothesis="H4",
        statement=("The Security Tax ST = alpha*z(dL) + beta*z(dC) partitions "
                   "configurations into interpretable governance-policy bands."),
        tests=[full_vs_g],
        intervals=intervals,
        extras={
            "bands": {"low": cfg.st_band_low, "high": cfg.st_band_high},
            "weights": {"alpha": cfg.st_alpha, "beta": cfg.st_beta},
            "distribution": distribution,
            "by_tier": {
                tier: {c: round(_median(v), 4) for c, v in cells.items()}
                for tier, cells in sorted(by_tier.items())
            },
            "alpha_sensitivity": alpha_sensitivity(result),
        },
        verdict=("SUPPORTED" if distribution else "NOT SUPPORTED"),
    )


def _st_vector(result: AblationResult, cell: str) -> List[float]:
    """Security-Tax values for one cell, ordered by scenario id."""

    values = {st.scenario_id: st.security_tax
              for st in result.security_tax if st.cell == cell}
    return [values[sid] for sid in sorted(values)]


def alpha_sensitivity(result: AblationResult,
                      alphas: Sequence[float] = (0.0, 0.25, 0.5, 0.75, 1.0)
                      ) -> Dict[str, Dict[str, object]]:
    """Re-derive the policy bands across the Security-Tax weighting.

    ``alpha`` trades latency cost against token cost. The thesis pre-registers
    ``alpha = 0.5``; a recommendation that flips band under a modest reweighting
    is not a robust recommendation, so the sweep is reported alongside the
    primary result rather than as an afterthought.
    """

    cfg = result.config
    rows = [
        {"scenario_id": o.scenario_id, "tier": o.tier, "cell": o.cell,
         "latency_ms": o.latency_ms, "tokens": o.tokens}
        for o in result.observations
    ]

    out: Dict[str, Dict[str, object]] = {}
    for alpha in alphas:
        tax = compute_security_tax(
            rows, alpha=alpha, beta=round(1.0 - alpha, 6),
            band_low=cfg.st_band_low, band_high=cfg.st_band_high,
        )
        per_cell: Dict[str, List[float]] = {}
        for st in tax:
            per_cell.setdefault(st.cell, []).append(st.security_tax)
        out[f"alpha={alpha:g}"] = {
            cell: {
                "median_st": round(_median(v), 4),
                "band": _band_for(_median(v), cfg.st_band_low, cfg.st_band_high),
            }
            for cell, v in sorted(per_cell.items())
        }
    return out


def _band_for(st: float, low: float, high: float) -> str:
    if st < low:
        return "full-governance"
    if st > high:
        return "minimal-governance"
    return "adaptive-governance"


def _sd(xs: Sequence[float]) -> float:
    from .stats import _std
    return _std(xs)


def _q(xs: Sequence[float], q: float) -> float:
    from .stats import _quantile
    return _quantile(xs, q)


# --------------------------------------------------------------------------- #
# The confirmatory family
# --------------------------------------------------------------------------- #
#: Test names that form the pre-registered confirmatory family. Everything else
#: reported by this module is exploratory.
CONFIRMATORY = (
    "H1 | G=0: Baseline -> V-only",
    "H1 | G=1: G-only -> Full",
    "H2 | V=0: latency, Baseline -> G-only",
    "H2 | V=1: latency, V-only -> Full",
    "H2: token consumption, ungoverned -> governed",
    "H3: V x G interaction on latency (ms)",
)


def run_all(result: AblationResult) -> Dict[str, object]:
    """Test H1-H4 and apply Holm-Bonferroni across the confirmatory family."""

    h1, h2, h3, h4 = test_h1(result), test_h2(result), test_h3(result), test_h4(result)

    every_test = [t for h in (h1, h2, h3, h4) for t in h.tests]
    family = [t for t in every_test if t.name in CONFIRMATORY]
    holm_bonferroni(family)

    # Re-derive verdicts from the adjusted p-values, so a hypothesis is only
    # reported as supported if it survives the multiplicity correction.
    adjusted = {t.name: t.p_adjusted for t in family}
    h1.verdict = _verdict(
        [adjusted.get("H1 | G=0: Baseline -> V-only"),
         adjusted.get("H1 | G=1: G-only -> Full")],
        h1.intervals["validation_main_effect_accuracy"],
    )
    h2.verdict = _verdict(
        [adjusted.get("H2 | V=0: latency, Baseline -> G-only"),
         adjusted.get("H2 | V=1: latency, V-only -> Full"),
         adjusted.get("H2: token consumption, ungoverned -> governed")],
        h2.intervals["governance_main_effect_latency_ms"],
    )
    h3.verdict = _verdict(
        [adjusted.get("H3: V x G interaction on latency (ms)")],
        h3.intervals["interaction_latency_ms"],
    )

    return {
        "n_observations": len(result.observations),
        "n_scenarios": len(scenario_ids(result)),
        "confirmatory_family_size": len(family),
        "multiplicity_correction": "Holm-Bonferroni",
        "H1": h1.as_dict(),
        "H2": h2.as_dict(),
        "H3": h3.as_dict(),
        "H4": h4.as_dict(),
    }


def _verdict(adjusted_ps: Sequence[Optional[float]], interval: Interval) -> str:
    """A hypothesis is supported only if every confirmatory test survives Holm
    *and* the effect interval excludes zero."""

    if any(p is None for p in adjusted_ps):
        return "INCONCLUSIVE"
    if all(p < 0.05 for p in adjusted_ps) and interval.excludes_zero():
        return "SUPPORTED"
    return "NOT SUPPORTED"
