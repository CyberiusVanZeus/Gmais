"""Performance metrics and Security-Tax computation (Section 3.3.4 / 3.3.5).

Implements the confusion-matrix family (Equations 3.3-3.6), the Brier
calibration score (Equation 3.7) and the dimensionally normalised Security Tax
(Equations 3.2 / 3.8). Pure-stdlib so the core measurement pipeline runs without
numpy/scipy; the heavier Bayesian/non-parametric inference lives in
:mod:`gmais.analysis` and degrades gracefully when scipy is absent.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence


# --------------------------------------------------------------------------- #
# Confusion matrix and derived metrics (Equations 3.3-3.6)
# --------------------------------------------------------------------------- #
@dataclass
class ConfusionMatrix:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0

    def add(self, predicted_positive: bool, actual_positive: bool) -> None:
        if actual_positive and predicted_positive:
            self.tp += 1
        elif actual_positive and not predicted_positive:
            self.fn += 1
        elif not actual_positive and predicted_positive:
            self.fp += 1
        else:
            self.tn += 1

    @property
    def total(self) -> int:
        return self.tp + self.fp + self.fn + self.tn

    @property
    def accuracy(self) -> float:
        return (self.tp + self.tn) / self.total if self.total else 0.0

    @property
    def precision(self) -> float:
        denom = self.tp + self.fp
        return self.tp / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.tp + self.fn
        return self.tp / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    def as_dict(self) -> Dict[str, float]:
        return {
            "tp": self.tp, "fp": self.fp, "fn": self.fn, "tn": self.tn,
            "accuracy": round(self.accuracy, 4),
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
        }


def injection_confusion(
    all_claim_ids: Sequence[str],
    gold_injected: Iterable[str],
    detected: Iterable[str],
    cm: ConfusionMatrix | None = None,
) -> ConfusionMatrix:
    """Accumulate misinformation-detection outcomes at the claim level."""

    cm = cm or ConfusionMatrix()
    gold = set(gold_injected)
    pred = set(detected)
    for cid in all_claim_ids:
        cm.add(predicted_positive=cid in pred, actual_positive=cid in gold)
    return cm


def brier_score(confidences: Sequence[float], outcomes: Sequence[int]) -> float:
    """Equation 3.7: mean squared error of probabilistic confidence."""

    if not confidences:
        return 0.0
    return round(
        sum((p - o) ** 2 for p, o in zip(confidences, outcomes)) / len(confidences), 4
    )


# --------------------------------------------------------------------------- #
# Security Tax (Equations 3.2 / 3.8)
# --------------------------------------------------------------------------- #
def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs: Sequence[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def zscore(value: float, mean: float, std: float) -> float:
    """Condition-wise z-standardisation; 0 when the distribution is degenerate."""

    if std <= 1e-12:
        return 0.0
    return (value - mean) / std


@dataclass
class SecurityTaxResult:
    scenario_id: str
    tier: str
    cell: str
    delta_latency_ms: float  # absolute differential (reported alongside ST)
    delta_tokens: float
    z_latency: float
    z_tokens: float
    security_tax: float
    band: str


def _band(st: float, low: float, high: float) -> str:
    if st < low:
        return "full-governance"
    if st > high:
        return "minimal-governance"
    return "adaptive-governance"


def compute_security_tax(
    observations: List[dict],
    *,
    alpha: float,
    beta: float,
    band_low: float,
    band_high: float,
    baseline_cell: str = "Baseline",
) -> List[SecurityTaxResult]:
    """Compute per-observation Security Tax (Algorithm 1, steps 5-6).

    ``observations`` is a list of dicts each with keys ``scenario_id``,
    ``tier``, ``cell``, ``latency_ms`` and ``tokens``. Baseline means are taken
    within tier; the resulting latency/token differentials are z-standardised
    within tier before the weighted composite is formed.
    """

    # Baseline means per tier (Validation absent, Governance absent).
    tiers = sorted({o["tier"] for o in observations})
    base_lat: Dict[str, float] = {}
    base_tok: Dict[str, float] = {}
    for tier in tiers:
        bl = [o["latency_ms"] for o in observations
              if o["tier"] == tier and o["cell"] == baseline_cell]
        bt = [o["tokens"] for o in observations
              if o["tier"] == tier and o["cell"] == baseline_cell]
        base_lat[tier] = _mean(bl)
        base_tok[tier] = _mean(bt)

    # Differentials relative to the tier baseline.
    enriched = []
    for o in observations:
        d_lat = o["latency_ms"] - base_lat[o["tier"]]
        d_tok = float(o["tokens"]) - base_tok[o["tier"]]
        enriched.append({**o, "d_lat": d_lat, "d_tok": d_tok})

    # Condition-wise z-scores of the differentials, within tier.
    results: List[SecurityTaxResult] = []
    for tier in tiers:
        rows = [e for e in enriched if e["tier"] == tier]
        lat_vals = [r["d_lat"] for r in rows]
        tok_vals = [r["d_tok"] for r in rows]
        lat_m, lat_s = _mean(lat_vals), _std(lat_vals)
        tok_m, tok_s = _mean(tok_vals), _std(tok_vals)
        for r in rows:
            zl = zscore(r["d_lat"], lat_m, lat_s)
            zt = zscore(r["d_tok"], tok_m, tok_s)
            st = alpha * zl + beta * zt
            results.append(
                SecurityTaxResult(
                    scenario_id=r["scenario_id"],
                    tier=tier,
                    cell=r["cell"],
                    delta_latency_ms=round(r["d_lat"], 3),
                    delta_tokens=round(r["d_tok"], 1),
                    z_latency=round(zl, 4),
                    z_tokens=round(zt, 4),
                    security_tax=round(st, 4),
                    band=_band(st, band_low, band_high),
                )
            )
    return results
