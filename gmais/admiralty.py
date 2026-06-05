"""Admiralty Code source grading (AJP-2.1).

The NATO Admiralty System grades every source on two *independent* axes:

* **Reliability** of the source: A (completely reliable) -> E (unreliable),
  with F = reliability cannot be judged.
* **Credibility** of the information: 1 (confirmed) -> 5 (improbable),
  with 6 = credibility cannot be judged.

Section 2.3.6 / 3.3 of the thesis adopts the *normative* operationalisation:
the Validator assesses the two dimensions independently rather than letting one
collapse into the other (the empirically documented human failure mode of
Baker et al., 1968). This module therefore grades reliability and credibility
through separate code paths and never lets one read the other's result.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import ADMIRALTY_CREDIBILITY, ADMIRALTY_RELIABILITY

# Numeric confidence contributed by each axis. The two maps are deliberately
# kept separate to preserve dimensional independence.
_RELIABILITY_SCORE = {"A": 1.00, "B": 0.80, "C": 0.60, "D": 0.40, "E": 0.20, "F": 0.50}
_CREDIBILITY_SCORE = {"1": 1.00, "2": 0.80, "3": 0.60, "4": 0.40, "5": 0.20, "6": 0.50}


@dataclass(frozen=True)
class AdmiraltyGrade:
    """An A1..F6 Admiralty grade with a derived scalar confidence."""

    reliability: str
    credibility: str

    def __post_init__(self) -> None:
        if self.reliability not in ADMIRALTY_RELIABILITY:
            raise ValueError(f"Invalid reliability letter: {self.reliability!r}")
        if self.credibility not in ADMIRALTY_CREDIBILITY:
            raise ValueError(f"Invalid credibility digit: {self.credibility!r}")

    @property
    def code(self) -> str:
        return f"{self.reliability}{self.credibility}"

    @property
    def confidence(self) -> float:
        """Geometric mean of the two axis scores in [0, 1].

        A geometric mean (rather than arithmetic) means a catastrophic grade on
        either axis drags confidence down, which matches tradecraft intuition:
        a perfectly reliable source reporting an improbable claim is still low
        confidence.
        """

        r = _RELIABILITY_SCORE[self.reliability]
        c = _CREDIBILITY_SCORE[self.credibility]
        return round((r * c) ** 0.5, 4)

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return f"{self.code} (conf={self.confidence:.2f})"


def _grade_reliability(provenance: str, corroboration: int) -> str:
    """Assess *source* reliability only. Must not consult claim plausibility."""

    table = {
        "official": "A",
        "established_media": "B",
        "ngo": "B",
        "expert": "B",
        "social_media": "D",
        "anonymous": "E",
        "unknown": "F",
    }
    letter = table.get(provenance, "C")
    # A corroborated channel may be promoted by at most one grade.
    if corroboration >= 2 and letter in ("B", "C", "D"):
        letter = chr(ord(letter) - 1)
    return letter


def _grade_credibility(corroboration: int, contradicted: bool, plausible: bool) -> str:
    """Assess *information* credibility only. Must not consult source identity."""

    if contradicted:
        return "5"  # improbable: conflicts with established evidence
    if corroboration >= 2 and plausible:
        return "1"  # confirmed by independent sources
    if corroboration == 1 and plausible:
        return "2"  # probably true
    if plausible:
        return "3"  # possibly true
    return "4"  # doubtful


def grade_source(source: dict) -> AdmiraltyGrade:
    """Grade a source description into an Admiralty code.

    ``source`` is a mapping with keys ``provenance`` (str), ``corroboration``
    (int, count of independent corroborating sources), ``contradicted`` (bool)
    and ``plausible`` (bool). Reliability and credibility are computed by
    independent functions to enforce the dimensional-independence constraint.
    """

    provenance = source.get("provenance", "unknown")
    corroboration = int(source.get("corroboration", 0))
    contradicted = bool(source.get("contradicted", False))
    plausible = bool(source.get("plausible", True))

    reliability = _grade_reliability(provenance, corroboration)
    credibility = _grade_credibility(corroboration, contradicted, plausible)
    return AdmiraltyGrade(reliability, credibility)
