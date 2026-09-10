"""Pre-registered observation-noise model (Section 3.2.4).

Why this module exists
----------------------
GMAIS implements its tradecraft primitives as *deterministic functions of the
source record*: :func:`gmais.admiralty.grade_source` maps a provenance string
and a corroboration count onto an Admiralty grade with no stochastic component.
Run unperturbed, the corpus generator emits injected claims that are uniformly
weak-provenance, uncorroborated and contradicted, so the Validator's reliability
floor separates them from genuine claims *perfectly*. The resulting campaign
reports detection F1 of exactly 0.000 without validation and exactly 1.000 with
it, and every paired test returns p at the floating-point floor. Those numbers
measure the corpus generator, not the architecture.

The remedy is not to weaken the architecture but to stop assuming an idealised
observation channel. This module injects the three error modes that the
literature documents for real source grading and real agent discourse:

1. **Grading error.** Human and model graders shift an Admiralty axis by one
   step at a non-trivial rate, and do so on the two axes semi-independently
   (Baker, McKendry & Mace, 1968; Section 2.3.5). ``grading_error_rate``.
2. **Injection camouflage.** Competent adversaries do not publish through
   obviously anonymous channels; a fraction of injected claims arrive laundered
   through plausible-looking, apparently corroborated provenance
   (Section 3.2.3). ``injection_camouflage_rate``.
3. **Provenance degradation.** Genuine reporting is not uniformly well-sourced;
   a fraction arrives single-sourced or attributed to a channel the grader
   cannot place. ``provenance_degradation_rate``.

A fourth rate, ``peer_anchoring_rate``, is not an observation error but the
behavioural mechanism the Governance Layer exists to interrupt: when a Worker
receives peer synthesis that still names the actor, it herds onto the
entity-anchored hypothesis (Section 3.3.1). Need-to-know redaction removes the
entity label, so this rate is the channel through which governance can move
analytical accuracy, and therefore the channel that produces the V x G
interaction of H3.

Determinism contract
--------------------
Every draw is a pure function of ``(campaign_seed, stream, key parts)`` taken
through SHA-256. It follows that:

* a campaign is bit-for-bit reproducible from its seed alone, satisfying
  Algorithm 1 step 3;
* the perturbation applied to a given claim is **identical across all four
  factorial cells**, so the ablation contrast remains a pure function of
  configuration and the repeated-measures pairing that the Friedman and
  Wilcoxon tests rely on is preserved; and
* no global RNG state is consumed, so thread scheduling in the concurrent
  Worker tier cannot perturb the draw sequence.

Set ``GMAISConfig.noise_enabled = False`` to recover the idealised
observation channel (used by the test-suite determinism checks).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Dict, List, Tuple

from .config import ADMIRALTY_CREDIBILITY, ADMIRALTY_RELIABILITY, GMAISConfig

#: Provenance labels an adversary can plausibly imitate when laundering an
#: injected claim, and the degraded labels genuine reporting can fall back to.
_CAMOUFLAGE_PROVENANCE: Tuple[str, ...] = ("established_media", "expert", "ngo")
_DEGRADED_PROVENANCE: Tuple[str, ...] = ("social_media", "unknown")


def _unit(seed: int, stream: str, *parts: object) -> float:
    """A uniform draw in [0, 1) determined entirely by its arguments."""

    key = "|".join([str(seed), stream, *(str(p) for p in parts)]).encode("utf-8")
    digest = hashlib.sha256(key).digest()
    return int.from_bytes(digest[:8], "big") / float(1 << 64)


def _choice(seed: int, stream: str, options, *parts: object):
    """Deterministically select one of ``options``."""

    return options[int(_unit(seed, stream, *parts) * len(options)) % len(options)]


@dataclass
class NoiseModel:
    """Seeded observation noise shared across every cell of the ablation."""

    seed: int
    grading_error_rate: float = 0.0
    injection_camouflage_rate: float = 0.0
    provenance_degradation_rate: float = 0.0
    peer_anchoring_rate: float = 0.0
    enabled: bool = True

    @classmethod
    def from_config(cls, config: GMAISConfig) -> "NoiseModel":
        return cls(
            seed=config.seed,
            grading_error_rate=config.grading_error_rate,
            injection_camouflage_rate=config.injection_camouflage_rate,
            provenance_degradation_rate=config.provenance_degradation_rate,
            peer_anchoring_rate=config.peer_anchoring_rate,
            enabled=config.noise_enabled,
        )

    @classmethod
    def disabled(cls, seed: int = 0) -> "NoiseModel":
        """The idealised observation channel (no perturbation)."""

        return cls(seed=seed, enabled=False)

    # ------------------------------------------------------------------ #
    # 1. Observation channel: how a claim's source record presents
    # ------------------------------------------------------------------ #
    def observed_source(self, sid: str, cid: str, source: dict,
                        is_injected: bool) -> dict:
        """Return the source record *as the system observes it*.

        Ground truth (``Claim.is_injected``) is untouched; only the observable
        provenance record is perturbed, so the GTKG remains the authoritative
        reference and detection genuinely can fail.
        """

        if not self.enabled:
            return source

        observed = dict(source)
        if is_injected:
            if _unit(self.seed, "camouflage", sid, cid) < self.injection_camouflage_rate:
                # Laundered: plausible channel, apparent independent corroboration,
                # and no overt contradiction for the grader to catch.
                observed["provenance"] = _choice(
                    self.seed, "camouflage-prov", _CAMOUFLAGE_PROVENANCE, sid, cid
                )
                observed["corroboration"] = 2
                observed["contradicted"] = False
                observed["plausible"] = True
        else:
            if _unit(self.seed, "degrade", sid, cid) < self.provenance_degradation_rate:
                # Genuine but poorly sourced: single-sourced via a weak channel.
                observed["provenance"] = _choice(
                    self.seed, "degrade-prov", _DEGRADED_PROVENANCE, sid, cid
                )
                observed["corroboration"] = 0
        return observed

    # ------------------------------------------------------------------ #
    # 2. Grader channel: one-step slips on the two Admiralty axes
    # ------------------------------------------------------------------ #
    def perturb_grade(self, sid: str, cid: str, reliability: str,
                      credibility: str) -> Tuple[str, str]:
        """Apply independent one-step grading slips to an Admiralty grade.

        The two axes are perturbed through separate draws, preserving the
        dimensional-independence constraint of Section 2.3.6: a slip on
        reliability carries no information about a slip on credibility.
        """

        if not self.enabled:
            return reliability, credibility

        rel = self._slip(
            ADMIRALTY_RELIABILITY[:5], reliability, "grade-rel", sid, cid
        )
        cred = self._slip(
            ADMIRALTY_CREDIBILITY[:5], credibility, "grade-cred", sid, cid
        )
        return rel, cred

    def _slip(self, ladder: Tuple[str, ...], value: str, stream: str,
              *parts: object) -> str:
        """Shift ``value`` one rung along ``ladder`` with probability p."""

        if value not in ladder:  # 'F' / '6' mean "cannot be judged" - never slip.
            return value
        draw = _unit(self.seed, stream, *parts)
        if draw >= self.grading_error_rate:
            return value
        idx = ladder.index(value)
        # Direction from the residual entropy of the same draw, so a slip is
        # equally likely to be optimistic or pessimistic.
        direction = 1 if (draw / max(self.grading_error_rate, 1e-12)) >= 0.5 else -1
        return ladder[min(len(ladder) - 1, max(0, idx + direction))]

    # ------------------------------------------------------------------ #
    # 3. Behavioural channel: peer anchoring under unredacted traffic
    # ------------------------------------------------------------------ #
    def worker_anchors(self, sid: str, worker_id: int) -> bool:
        """Does this Worker herd onto the entity-anchored hypothesis?

        Only consulted when peer traffic reaches the Worker with named entities
        intact, i.e. in the ungoverned cells. Under governance the Governance
        Layer masks the entity label before transmission and the anchor is
        unavailable, which is precisely the effect H3 tests for.
        """

        if not self.enabled:
            return False
        return _unit(self.seed, "anchor", sid, worker_id) < self.peer_anchoring_rate

    # ------------------------------------------------------------------ #
    # Reporting
    # ------------------------------------------------------------------ #
    def manifest(self) -> Dict[str, object]:
        """The pre-registered rates, for the reproducibility manifest."""

        return {
            "enabled": self.enabled,
            "seed": self.seed,
            "grading_error_rate": self.grading_error_rate,
            "injection_camouflage_rate": self.injection_camouflage_rate,
            "provenance_degradation_rate": self.provenance_degradation_rate,
            "peer_anchoring_rate": self.peer_anchoring_rate,
        }

    def corpus_diagnostics(self, corpus: List) -> Dict[str, float]:
        """How many claims the observation channel actually perturbed.

        Reported in the results package so a reviewer can confirm the realised
        perturbation matches the pre-registered rates.
        """

        camouflaged = degraded = injected = genuine = 0
        for scenario in corpus:
            for claim in scenario.claims:
                observed = self.observed_source(
                    scenario.sid, claim.cid, claim.source, claim.is_injected
                )
                if claim.is_injected:
                    injected += 1
                    if observed != claim.source:
                        camouflaged += 1
                else:
                    genuine += 1
                    if observed != claim.source:
                        degraded += 1
        return {
            "injected_claims": injected,
            "camouflaged_claims": camouflaged,
            "realised_camouflage_rate": round(camouflaged / injected, 4) if injected else 0.0,
            "genuine_claims": genuine,
            "degraded_claims": degraded,
            "realised_degradation_rate": round(degraded / genuine, 4) if genuine else 0.0,
        }
