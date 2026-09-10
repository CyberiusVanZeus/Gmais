"""Inferential statistics for H1-H4 (Section 3.3.6).

The campaign is a **within-scenario repeated-measures 2x2 design**: every
scenario in the corpus is taken through all four factorial cells, so the four
observations of a scenario share its complexity, its claim set and its
observation noise. The only thing that varies across them is the configuration.
That pairing is the design's main source of power and it dictates the analysis:
every test here is a paired or repeated-measures test computed on
within-scenario contrasts, never a between-groups test on pooled cells.

What each hypothesis is tested with
-----------------------------------
=====  ===================================  =====================================
H1     Validation raises analytical accuracy  Exact McNemar on discordant pairs,
                                              at both levels of governance, plus a
                                              paired-bootstrap CI on the main effect
H2     Governance raises latency and tokens   Wilcoxon signed-rank with
                                              Hodges-Lehmann shift and matched
                                              rank-biserial effect size
H3     Validation x Governance interact       One-sample Wilcoxon on the
                                              per-scenario interaction contrast
                                              (Full - V) - (G - Baseline)
H4     Security Tax maps to policy bands      Band proportions with Wilson
                                              intervals, plus an alpha-sensitivity
                                              sweep of the band assignment
=====  ===================================  =====================================

Multiplicity is controlled with Holm-Bonferroni across the confirmatory family.
Effect sizes are reported for every test, because with 135 scenarios per cell a
p-value alone says little: the design is powered to detect differences far
smaller than the ones that would matter operationally.

scipy supplies the reference implementations of Wilcoxon and Friedman; the
module degrades to exact stdlib implementations for the binomial and bootstrap
paths so the confirmatory results remain computable without it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from itertools import combinations
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .ablation import AblationResult

CELL_ORDER = ("Baseline", "V-only", "G-only", "Full")

#: Bootstrap resamples for every interval reported. Fixed, and seeded from the
#: campaign seed, so intervals are reproducible to the last digit.
N_BOOTSTRAP = 10_000


# --------------------------------------------------------------------------- #
# Small stdlib statistics helpers
# --------------------------------------------------------------------------- #
def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs: Sequence[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _median(xs: Sequence[float]) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def _quantile(xs: Sequence[float], q: float) -> float:
    """Linear-interpolation quantile (NumPy's default 'linear' method)."""

    if not xs:
        return 0.0
    s = sorted(xs)
    if len(s) == 1:
        return s[0]
    pos = q * (len(s) - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def _binom_sf(k: int, n: int, p: float = 0.5) -> float:
    """P(X >= k) for X ~ Binomial(n, p), computed exactly."""

    total = 0.0
    for i in range(k, n + 1):
        total += math.comb(n, i) * (p ** i) * ((1 - p) ** (n - i))
    return min(1.0, total)


@dataclass
class Interval:
    """A point estimate with a confidence interval."""

    estimate: float
    low: float
    high: float
    level: float = 0.95

    def excludes_zero(self) -> bool:
        return (self.low > 0.0) or (self.high < 0.0)

    def as_dict(self) -> Dict[str, float]:
        return {
            "estimate": round(self.estimate, 6),
            "ci_low": round(self.low, 6),
            "ci_high": round(self.high, 6),
            "level": self.level,
        }

    def __str__(self) -> str:
        return f"{self.estimate:+.4f} [{self.low:+.4f}, {self.high:+.4f}]"


# --------------------------------------------------------------------------- #
# Bootstrap
# --------------------------------------------------------------------------- #
def bootstrap_ci(values: Sequence[float], statistic: Callable[[Sequence[float]], float],
                 *, seed: int, n_boot: int = N_BOOTSTRAP,
                 level: float = 0.95) -> Interval:
    """Percentile bootstrap interval for ``statistic`` over ``values``.

    The resampling unit is the scenario, which is the unit of independence in
    this design: within a scenario the four cell observations are dependent by
    construction, so resampling observations rather than scenarios would
    understate the interval.
    """

    n = len(values)
    if n == 0:
        return Interval(0.0, 0.0, 0.0, level)
    point = statistic(values)
    if n == 1:
        return Interval(point, point, point, level)

    tail = (1.0 - level) / 2.0

    # NumPy fast path. The resampling is done as a single (n_boot x n) index
    # draw and the statistic applied along one axis, which keeps a 10,000-
    # resample interval to milliseconds. Only the two statistics this module
    # actually bootstraps -- the mean and the median -- have vectorised forms;
    # anything else falls through to the loop below.
    vectorised = {_mean: "mean", _median: "median"}.get(statistic)
    if vectorised is not None:
        try:
            import numpy as _np

            rng = _np.random.default_rng(seed)
            data = _np.asarray(values, dtype=float)
            idx = rng.integers(0, n, size=(n_boot, n))
            resampled = data[idx]
            draws = (resampled.mean(axis=1) if vectorised == "mean"
                     else _np.median(resampled, axis=1))
            return Interval(
                point,
                float(_np.quantile(draws, tail)),
                float(_np.quantile(draws, 1.0 - tail)),
                level,
            )
        except ImportError:  # pragma: no cover - numpy optional
            pass

    import random as _random

    rng = _random.Random(seed)
    draws: List[float] = []
    for _ in range(n_boot):
        sample = [values[int(rng.random() * n)] for _ in range(n)]
        draws.append(statistic(sample))

    return Interval(point, _quantile(draws, tail), _quantile(draws, 1.0 - tail), level)


# --------------------------------------------------------------------------- #
# Paired tests
# --------------------------------------------------------------------------- #
@dataclass
class PairedTest:
    """Result of a paired comparison between two factorial cells."""

    name: str
    n_pairs: int
    test: str
    statistic: float
    p_value: float
    p_adjusted: Optional[float] = None
    effect_size: float = 0.0
    effect_name: str = ""
    shift: Optional[Interval] = None  # Hodges-Lehmann / mean difference + CI
    detail: Dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, object]:
        out: Dict[str, object] = {
            "name": self.name,
            "n_pairs": self.n_pairs,
            "test": self.test,
            "statistic": round(self.statistic, 6),
            "p_value": self.p_value,
            "effect_size": round(self.effect_size, 6),
            "effect_name": self.effect_name,
        }
        if self.p_adjusted is not None:
            out["p_adjusted"] = self.p_adjusted
        if self.shift is not None:
            out["shift"] = self.shift.as_dict()
        if self.detail:
            out["detail"] = self.detail
        return out


def mcnemar_exact(a: Sequence[int], b: Sequence[int], *, name: str) -> PairedTest:
    """Exact McNemar test on paired binary outcomes.

    ``a`` and ``b`` are matched 0/1 correctness vectors. Concordant pairs carry
    no information about the direction of the effect; the exact binomial test on
    the discordant pairs is used rather than the chi-square approximation, which
    is unreliable when discordant counts are small.
    """

    n01 = sum(1 for x, y in zip(a, b) if x == 0 and y == 1)  # b better
    n10 = sum(1 for x, y in zip(a, b) if x == 1 and y == 0)  # a better
    discordant = n01 + n10

    if discordant == 0:
        return PairedTest(
            name=name, n_pairs=len(a), test="McNemar (exact)", statistic=0.0,
            p_value=1.0, effect_size=0.0, effect_name="odds ratio",
            detail={"n01": n01, "n10": n10, "discordant": 0},
        )

    k = max(n01, n10)
    p = min(1.0, 2.0 * _binom_sf(k, discordant, 0.5))
    # Odds ratio of the discordant cells, with the Haldane-Anscombe correction
    # so it stays finite when one discordant cell is empty.
    odds_ratio = (n01 + 0.5) / (n10 + 0.5)
    return PairedTest(
        name=name,
        n_pairs=len(a),
        test="McNemar (exact)",
        statistic=float(k),
        p_value=p,
        effect_size=odds_ratio,
        effect_name="odds ratio (discordant)",
        detail={
            "n01_b_correct_only": n01,
            "n10_a_correct_only": n10,
            "discordant": discordant,
            "proportion_a": round(_mean(a), 6),
            "proportion_b": round(_mean(b), 6),
        },
    )


def _walsh_averages(diffs: Sequence[float]) -> List[float]:
    """The n(n+1)/2 pairwise averages (d_i + d_j)/2 for i <= j, sorted."""

    n = len(diffs)
    try:
        import numpy as _np

        data = _np.asarray(diffs, dtype=float)
        i, j = _np.triu_indices(n)
        return _np.sort((data[i] + data[j]) / 2.0).tolist()
    except ImportError:  # pragma: no cover - numpy optional
        return sorted((diffs[i] + diffs[j]) / 2.0
                      for i in range(n) for j in range(i, n))


def _hodges_lehmann(diffs: Sequence[float]) -> float:
    """Median of the Walsh averages: the location estimator matched to Wilcoxon.

    Reported instead of the mean difference because the Wilcoxon signed-rank
    test is a test about this quantity, not about the mean.
    """

    n = len(diffs)
    if n == 0:
        return 0.0
    if n > 3000:  # the O(n^2) Walsh set stops being worth materialising
        return _median(diffs)
    return _median(_walsh_averages(diffs))


def hodges_lehmann_ci(diffs: Sequence[float], *, level: float = 0.95) -> Interval:
    """Exact distribution-free interval for the Hodges-Lehmann shift.

    The confidence interval that *matches* the Wilcoxon signed-rank test is not
    a bootstrap interval: it is read directly off the order statistics of the
    Walsh averages, with the cut point set by the signed-rank null distribution.
    Using it rather than resampling the estimator is both the textbook procedure
    (Hollander & Wolfe, 1999, Sec. 3.2) and dramatically cheaper -- bootstrapping
    an O(n^2) estimator costs O(B * n^2), which for the campaign's 135 paired
    scenarios and 10,000 resamples is on the order of 10^8 operations per
    interval.

    The cut point uses the normal approximation to the signed-rank distribution,
    which is accurate well below the sample sizes used here.
    """

    n = len(diffs)
    if n == 0:
        return Interval(0.0, 0.0, 0.0, level)
    point = _hodges_lehmann(diffs)
    if n == 1:
        return Interval(point, point, point, level)

    walsh = _walsh_averages(diffs)
    total = len(walsh)  # n(n+1)/2

    z = 1.959963984540054 if abs(level - 0.95) < 1e-9 else _z_for(level)
    mean_w = n * (n + 1) / 4.0
    sd_w = math.sqrt(n * (n + 1) * (2 * n + 1) / 24.0)
    k = int(math.floor(mean_w - z * sd_w))
    k = max(0, min(k, total // 2 - 1)) if total >= 2 else 0

    return Interval(point, walsh[k], walsh[total - 1 - k], level)


def wilcoxon_paired(a: Sequence[float], b: Sequence[float], *, name: str,
                    seed: int) -> PairedTest:
    """Wilcoxon signed-rank test of b - a, with a matched effect size.

    Reports the matched-pairs rank-biserial correlation (the standardised
    difference between positive and negative rank sums), which is the effect
    size the signed-rank statistic actually implies, plus a bootstrap interval
    on the Hodges-Lehmann shift.
    """

    diffs = [y - x for x, y in zip(a, b)]
    nonzero = [d for d in diffs if d != 0.0]
    n = len(nonzero)

    if n == 0:
        return PairedTest(
            name=name, n_pairs=len(diffs), test="Wilcoxon signed-rank",
            statistic=0.0, p_value=1.0, effect_size=0.0,
            effect_name="rank-biserial r",
            shift=Interval(0.0, 0.0, 0.0),
            detail={"note": "all paired differences are exactly zero"},
        )

    statistic = float("nan")
    p_value = float("nan")
    try:
        from scipy import stats as _st  # type: ignore

        res = _st.wilcoxon(nonzero, alternative="two-sided", zero_method="wilcox")
        statistic, p_value = float(res.statistic), float(res.pvalue)
    except Exception:  # pragma: no cover - scipy optional
        # Normal approximation with a continuity correction.
        ranks = _rank_abs(nonzero)
        w_plus = sum(r for d, r in zip(nonzero, ranks) if d > 0)
        w_minus = sum(r for d, r in zip(nonzero, ranks) if d < 0)
        statistic = float(min(w_plus, w_minus))
        mu = n * (n + 1) / 4.0
        sigma = math.sqrt(n * (n + 1) * (2 * n + 1) / 24.0)
        z = (statistic - mu + 0.5) / sigma if sigma else 0.0
        p_value = 2.0 * (1.0 - _norm_cdf(abs(z)))

    ranks = _rank_abs(nonzero)
    w_plus = sum(r for d, r in zip(nonzero, ranks) if d > 0)
    w_minus = sum(r for d, r in zip(nonzero, ranks) if d < 0)
    total = w_plus + w_minus
    rank_biserial = (w_plus - w_minus) / total if total else 0.0

    # Exact signed-rank interval, not a bootstrap: see hodges_lehmann_ci.
    shift = hodges_lehmann_ci(diffs)

    return PairedTest(
        name=name,
        n_pairs=len(diffs),
        test="Wilcoxon signed-rank",
        statistic=statistic,
        p_value=p_value,
        effect_size=rank_biserial,
        effect_name="rank-biserial r",
        shift=shift,
        detail={
            "median_difference": round(_median(diffs), 6),
            "mean_difference": round(_mean(diffs), 6),
            "cohens_dz": round(_cohens_dz(diffs), 6),
            "n_nonzero": n,
        },
    )


def _rank_abs(values: Sequence[float]) -> List[float]:
    """Mid-ranks of |values|, matching the signed-rank tie convention."""

    indexed = sorted(range(len(values)), key=lambda i: abs(values[i]))
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j + 1 < len(indexed) and abs(values[indexed[j + 1]]) == abs(values[indexed[i]]):
            j += 1
        mid = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[indexed[k]] = mid
        i = j + 1
    return ranks


def _cohens_dz(diffs: Sequence[float]) -> float:
    """Paired standardised mean difference."""

    sd = _std(diffs)
    return _mean(diffs) / sd if sd > 1e-12 else 0.0


def _norm_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def cliffs_delta(a: Sequence[float], b: Sequence[float]) -> float:
    """Non-parametric dominance of b over a, in [-1, 1]."""

    if not a or not b:
        return 0.0
    greater = sum(1 for x in a for y in b if y > x)
    less = sum(1 for x in a for y in b if y < x)
    return (greater - less) / (len(a) * len(b))


# --------------------------------------------------------------------------- #
# Multiplicity control
# --------------------------------------------------------------------------- #
def holm_bonferroni(tests: Sequence[PairedTest]) -> List[PairedTest]:
    """Assign Holm-Bonferroni adjusted p-values in place, preserving order.

    Holm is used rather than Bonferroni because it is uniformly more powerful at
    the same familywise error rate, and rather than FDR because the confirmatory
    family here is small and the cost of a false positive on a governance
    recommendation is asymmetric.
    """

    order = sorted(range(len(tests)), key=lambda i: tests[i].p_value)
    m = len(tests)
    running = 0.0
    for rank, idx in enumerate(order):
        adjusted = min(1.0, tests[idx].p_value * (m - rank))
        running = max(running, adjusted)  # enforce monotonicity
        tests[idx].p_adjusted = running
    return list(tests)


# --------------------------------------------------------------------------- #
# Calibration: Brier score and its decomposition
# --------------------------------------------------------------------------- #
@dataclass
class BrierDecomposition:
    """Murphy's (1973) three-term decomposition of the Brier score.

    ``brier = reliability - resolution + uncertainty``. The decomposition is
    what makes a Brier score interpretable: a system can improve its score
    either by becoming better calibrated (lower reliability term) or by
    discriminating more sharply between outcomes (higher resolution), and the
    thesis's calibration claim is specifically about the former.
    """

    brier: float
    reliability: float
    resolution: float
    uncertainty: float
    n_bins: int
    bin_counts: List[int] = field(default_factory=list)
    bin_confidence: List[float] = field(default_factory=list)
    bin_outcome: List[float] = field(default_factory=list)

    def as_dict(self) -> Dict[str, object]:
        return {
            "brier": round(self.brier, 6),
            "reliability": round(self.reliability, 6),
            "resolution": round(self.resolution, 6),
            "uncertainty": round(self.uncertainty, 6),
            "decomposition_residual": round(
                self.brier - (self.reliability - self.resolution + self.uncertainty), 9
            ),
            "n_bins_occupied": sum(1 for c in self.bin_counts if c),
        }


def brier_decomposition(confidences: Sequence[float], outcomes: Sequence[int],
                        *, n_bins: int = 10) -> BrierDecomposition:
    """Decompose the Brier score into reliability, resolution and uncertainty."""

    n = len(confidences)
    if n == 0:
        return BrierDecomposition(0.0, 0.0, 0.0, 0.0, n_bins)

    brier = sum((p - o) ** 2 for p, o in zip(confidences, outcomes)) / n
    base_rate = _mean([float(o) for o in outcomes])
    uncertainty = base_rate * (1.0 - base_rate)

    # Murphy's identity is exact only on the calibration-refinement partition,
    # i.e. when forecasts are grouped by *distinct value* rather than into
    # fixed-width bins -- binning a continuous forecast leaves a within-bin
    # variance residual that breaks the identity. The reliability and
    # resolution terms are therefore computed on distinct forecast values, and
    # the fixed-width bins below are retained only for the reliability diagram.
    groups: Dict[float, List[int]] = {}
    for p, o in zip(confidences, outcomes):
        groups.setdefault(p, []).append(int(o))

    reliability = resolution = 0.0
    for forecast, outs in groups.items():
        weight = len(outs) / n
        observed = _mean([float(o) for o in outs])
        reliability += weight * (forecast - observed) ** 2
        resolution += weight * (observed - base_rate) ** 2

    bins: List[List[Tuple[float, int]]] = [[] for _ in range(n_bins)]
    for p, o in zip(confidences, outcomes):
        idx = min(n_bins - 1, max(0, int(p * n_bins)))
        bins[idx].append((p, o))

    counts, bin_conf, bin_out = [], [], []
    for bucket in bins:
        counts.append(len(bucket))
        if not bucket:
            bin_conf.append(float("nan"))
            bin_out.append(float("nan"))
            continue
        bin_conf.append(_mean([p for p, _ in bucket]))
        bin_out.append(_mean([float(o) for _, o in bucket]))

    return BrierDecomposition(
        brier=brier, reliability=reliability, resolution=resolution,
        uncertainty=uncertainty, n_bins=n_bins, bin_counts=counts,
        bin_confidence=bin_conf, bin_outcome=bin_out,
    )


# --------------------------------------------------------------------------- #
# Proportions
# --------------------------------------------------------------------------- #
def wilson_ci(successes: int, n: int, *, level: float = 0.95) -> Interval:
    """Wilson score interval for a binomial proportion.

    Preferred to the Wald interval, which misbehaves badly near 0 and 1 -- and
    several of the band proportions in H4 sit exactly there.
    """

    if n == 0:
        return Interval(0.0, 0.0, 0.0, level)
    z = 1.959963984540054 if abs(level - 0.95) < 1e-9 else _z_for(level)
    phat = successes / n
    denom = 1.0 + z * z / n
    centre = (phat + z * z / (2 * n)) / denom
    margin = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n)) / denom
    # At phat = 0 or 1 the corresponding bound is exactly 0 or 1; snap it so
    # floating-point residue does not leak a 1e-18 lower bound into a table.
    low = 0.0 if successes == 0 else max(0.0, centre - margin)
    high = 1.0 if successes == n else min(1.0, centre + margin)
    return Interval(phat, low, high, level)


def _z_for(level: float) -> float:
    """Inverse standard normal CDF at (1+level)/2, by bisection."""

    target = (1.0 + level) / 2.0
    lo, hi = 0.0, 10.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if _norm_cdf(mid) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0
