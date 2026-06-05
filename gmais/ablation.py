"""Algorithm 1: the GMAIS 2x2 factorial ablation (Section 3.3.3).

Drives every (scenario, cell) pair through the orchestrator under deterministic
seeding, grades each output against the GTKG, and assembles the observation
matrix that the Security-Tax and inference machinery consume. The structure
follows the thesis pseudocode: prepare scenarios (steps 1-2), fix the seed
(step 3), run the four cells over the corpus (step 4), then hand off to the
Security-Tax computation (steps 5-6) and analysis (steps 7-11).
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field
from typing import Dict, List

from .config import CELLS, GMAISConfig
from .gtkg import GroundTruthKnowledgeGraph
from .llm import build_backend
from .metrics import ConfusionMatrix, brier_score, compute_security_tax, injection_confusion
from .orchestrator import GMAISOrchestrator
from .scenarios import generate_corpus


@dataclass
class Observation:
    """One row of the observation matrix O (Algorithm 1 output)."""

    scenario_id: str
    tier: str
    cell: str
    validation: int
    governance: int
    latency_ms: float
    tokens: int
    correct: int
    confidence: float
    rubric_composite: float
    n_detected: int
    n_injected: int
    validator_iterations: int
    audit_intact: int


@dataclass
class AblationResult:
    config: GMAISConfig
    observations: List[Observation]
    security_tax: list  # List[SecurityTaxResult]
    per_cell_metrics: Dict[str, dict]

    def observation_dicts(self) -> List[dict]:
        return [asdict(o) for o in self.observations]


def run_ablation(config: GMAISConfig | None = None, *, db_path: str = ":memory:") -> AblationResult:
    """Execute the full factorial ablation and return the observation matrix."""

    config = config or GMAISConfig()

    # Steps 1-2: prepare scenarios and load ground truth.
    corpus = generate_corpus(config.seed, config.scenarios_per_tier)
    gtkg = GroundTruthKnowledgeGraph(db_path)
    gtkg.load_corpus(corpus)

    # Step 3: fix the random seed for the whole campaign.
    random.seed(config.seed)
    backend = build_backend(config.backend, seed=config.seed, model=config.model)
    orchestrator = GMAISOrchestrator(backend, config)

    # Step 4: iterate cells x scenarios.
    observations: List[Observation] = []
    per_cell: Dict[str, dict] = {
        cell.name: {
            "cm": ConfusionMatrix(),
            "confidences": [],
            "outcomes": [],
            "accuracy_hits": 0,
            "n": 0,
            "audit_failures": 0,
        }
        for cell in CELLS
    }

    for cell in CELLS:
        for scenario in corpus:
            result = orchestrator.analyze(scenario, cell)
            rubric = gtkg.score(
                scenario,
                predicted_hypothesis=result.predicted_hypothesis,
                detected_injection_cids=result.detected_injection_cids,
                accepted_cids=[c.cid for c in scenario.claims],
                confidence=result.confidence,
            )
            audit_intact = 1 if (result.governance is None or result.governance.audit_intact) else 0

            observations.append(
                Observation(
                    scenario_id=scenario.sid,
                    tier=scenario.tier,
                    cell=cell.name,
                    validation=int(cell.validation),
                    governance=int(cell.governance),
                    latency_ms=result.latency_ms,
                    tokens=result.tokens,
                    correct=int(result.correct),
                    confidence=result.confidence,
                    rubric_composite=rubric.composite,
                    n_detected=len(result.detected_injection_cids),
                    n_injected=len(result.gold_injection_cids),
                    validator_iterations=result.validator_iterations,
                    audit_intact=audit_intact,
                )
            )

            # Accumulate per-cell metrics.
            bucket = per_cell[cell.name]
            injection_confusion(
                [c.cid for c in scenario.claims],
                result.gold_injection_cids,
                result.detected_injection_cids,
                bucket["cm"],
            )
            bucket["confidences"].append(result.confidence)
            bucket["outcomes"].append(int(result.correct))
            bucket["accuracy_hits"] += int(result.correct)
            bucket["n"] += 1
            bucket["audit_failures"] += 0 if audit_intact else 1

    # Steps 5-6: Security Tax.
    sec_tax = compute_security_tax(
        [
            {"scenario_id": o.scenario_id, "tier": o.tier, "cell": o.cell,
             "latency_ms": o.latency_ms, "tokens": o.tokens}
            for o in observations
        ],
        alpha=config.st_alpha,
        beta=config.st_beta,
        band_low=config.st_band_low,
        band_high=config.st_band_high,
    )

    # Summarise per-cell metrics.
    per_cell_metrics: Dict[str, dict] = {}
    for name, b in per_cell.items():
        cm: ConfusionMatrix = b["cm"]
        per_cell_metrics[name] = {
            "n": b["n"],
            "hypothesis_accuracy": round(b["accuracy_hits"] / b["n"], 4) if b["n"] else 0.0,
            "brier_score": brier_score(b["confidences"], b["outcomes"]),
            "detection": cm.as_dict(),
            "audit_failures": b["audit_failures"],
            "mean_latency_ms": round(
                sum(o.latency_ms for o in observations if o.cell == name) / b["n"], 3
            ) if b["n"] else 0.0,
            "mean_tokens": round(
                sum(o.tokens for o in observations if o.cell == name) / b["n"], 1
            ) if b["n"] else 0.0,
        }

    gtkg.close()
    return AblationResult(
        config=config,
        observations=observations,
        security_tax=sec_tax,
        per_cell_metrics=per_cell_metrics,
    )
