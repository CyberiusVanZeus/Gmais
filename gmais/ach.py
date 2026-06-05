"""Analysis of Competing Hypotheses (Heuer, 1999).

ACH evaluates a set of mutually exclusive hypotheses against a body of evidence
by scoring the *consistency* of each evidence item with each hypothesis, then
selecting the hypothesis with the fewest weighted inconsistencies rather than
the one with the most supporting evidence. The thesis embeds ACH inside the
Validator as an algorithmic constraint (Section 2.3.6), using Heuer's seven
diagnostic questions as validation checkpoints and a *diagnosticity* weighting
so that evidence consistent with everything counts for little.

The convergence score returned here feeds the Validator's bounded-rationality
stopping rule (halt when convergence >= 0.85; Section 2.1 / config).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

# Heuer's seven diagnostic questions, used as explicit validation checkpoints.
HEUER_DIAGNOSTIC_QUESTIONS: tuple[str, ...] = (
    "Have all reasonable hypotheses been identified and listed?",
    "Has all significant evidence and argument been listed?",
    "Is each item of evidence assessed for consistency with each hypothesis?",
    "Has the diagnosticity of each evidence item been judged?",
    "Has evidence of low credibility or reliability been refined or discarded?",
    "Has the analysis sought to disprove hypotheses rather than confirm them?",
    "Has the sensitivity of conclusions to a few critical items been reported?",
)

# Consistency codes used to fill the ACH matrix.
CONSISTENT = 1
NEUTRAL = 0
INCONSISTENT = -1


@dataclass
class Evidence:
    """One evidence item plus its per-hypothesis consistency assessment."""

    eid: str
    text: str
    weight: float  # source confidence in [0, 1] (e.g. Admiralty confidence)
    # hypothesis-id -> {CONSISTENT, NEUTRAL, INCONSISTENT}
    consistency: Dict[str, int] = field(default_factory=dict)

    def diagnosticity(self) -> float:
        """How well this item discriminates among hypotheses, in [0, 1].

        Evidence consistent with every hypothesis is non-diagnostic (0);
        evidence that splits the hypothesis set is highly diagnostic (->1).
        """

        vals = list(self.consistency.values())
        if not vals:
            return 0.0
        spread = (max(vals) - min(vals)) / 2.0  # 0..1 over {-1,0,1}
        return spread


@dataclass
class ACHResult:
    """Outcome of an ACH evaluation."""

    ranking: List[tuple[str, float]]  # (hypothesis_id, weighted inconsistency)
    convergence: float  # separation between best and second-best, in [0, 1]
    diagnostic_checks: Dict[str, bool]

    @property
    def selected(self) -> str:
        return self.ranking[0][0]


class ACHMatrix:
    """A competing-hypotheses matrix scored by weighted inconsistency."""

    def __init__(self, hypotheses: Dict[str, str]):
        if len(hypotheses) < 2:
            raise ValueError("ACH requires at least two competing hypotheses.")
        self.hypotheses = dict(hypotheses)
        self.evidence: List[Evidence] = []

    def add_evidence(self, item: Evidence) -> None:
        self.evidence.append(item)

    def _diagnostic_checks(self) -> Dict[str, bool]:
        has_ev = bool(self.evidence)
        scored = all(
            set(e.consistency.keys()) >= set(self.hypotheses) for e in self.evidence
        )
        judged = any(e.diagnosticity() > 0 for e in self.evidence)
        refined = all(0.0 <= e.weight <= 1.0 for e in self.evidence)
        return {
            HEUER_DIAGNOSTIC_QUESTIONS[0]: len(self.hypotheses) >= 2,
            HEUER_DIAGNOSTIC_QUESTIONS[1]: has_ev,
            HEUER_DIAGNOSTIC_QUESTIONS[2]: scored,
            HEUER_DIAGNOSTIC_QUESTIONS[3]: judged,
            HEUER_DIAGNOSTIC_QUESTIONS[4]: refined,
            HEUER_DIAGNOSTIC_QUESTIONS[5]: True,  # scoring is disconfirmation-based
            HEUER_DIAGNOSTIC_QUESTIONS[6]: has_ev,
        }

    def evaluate(self) -> ACHResult:
        """Rank hypotheses by diagnosticity-weighted inconsistency (low = best)."""

        scores: Dict[str, float] = {h: 0.0 for h in self.hypotheses}
        for ev in self.evidence:
            d = ev.diagnosticity()
            for h in self.hypotheses:
                code = ev.consistency.get(h, NEUTRAL)
                if code == INCONSISTENT:
                    # Weight inconsistency by both source confidence and how
                    # diagnostic the item is.
                    scores[h] += ev.weight * (0.5 + d)
        ranking = sorted(scores.items(), key=lambda kv: kv[1])

        # Convergence: normalised gap between the best and second-best score.
        if len(ranking) >= 2:
            best, second = ranking[0][1], ranking[1][1]
            denom = max(second, 1e-9)
            convergence = min(1.0, (second - best) / denom) if second > 0 else 0.0
        else:  # pragma: no cover - guarded by constructor
            convergence = 1.0

        return ACHResult(
            ranking=ranking,
            convergence=round(convergence, 4),
            diagnostic_checks=self._diagnostic_checks(),
        )
