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
from .noise import NoiseModel
from .orchestrator import GMAISOrchestrator
from .scenarios import generate_corpus
from .timing import ComponentTimings, NullTimings, environment_manifest


@dataclass
class Observation:
    """One row of the observation matrix O (Algorithm 1 output)."""

    scenario_id: str
    tier: str
    cell: str
    validation: int
    governance: int
    # Modelled end-to-end cost (inference cost model + deployment governance
    # cost model) -- the quantity the pre-registered Security Tax is defined on.
    latency_ms: float
    tokens: int
    correct: int
    confidence: float
    rubric_composite: float
    n_detected: int
    n_injected: int
    validator_iterations: int
    audit_intact: int
    # --- Measured wall clock (time.perf_counter_ns), see gmais.timing ------ #
    measured_latency_ms: float = 0.0
    measured_governance_ms: float = 0.0
    measured_worker_ms: float = 0.0
    measured_validator_ms: float = 0.0
    measured_policy_ms: float = 0.0
    measured_audit_ms: float = 0.0
    measured_redaction_ms: float = 0.0
    measured_queue_ms: float = 0.0
    # --- Detection detail, needed for per-observation confusion analysis --- #
    n_true_positive: int = 0
    n_false_positive: int = 0
    n_claims: int = 0
    governed_events: int = 0
    # --- Bias-control channel (Section 3.3.1) ----------------------------- #
    anchored_workers: int = 0
    peer_bias_exposure: int = 0
    entities_redacted: int = 0


@dataclass
class AblationResult:
    config: GMAISConfig
    observations: List[Observation]
    security_tax: list  # List[SecurityTaxResult]
    per_cell_metrics: Dict[str, dict]
    #: Platform facts needed to interpret the measured wall-clock figures.
    environment: Dict[str, object] = field(default_factory=dict)
    #: Pre-registered noise rates and the perturbation they actually realised.
    noise_manifest: Dict[str, object] = field(default_factory=dict)
    #: Corpus-level ground-truth statistics (Section 3.2.1).
    corpus_stats: Dict[str, object] = field(default_factory=dict)

    def observation_dicts(self) -> List[dict]:
        return [asdict(o) for o in self.observations]


def run_ablation(config: GMAISConfig | None = None, *, db_path: str = ":memory:",
                 checkpoint_path: str | None = None, progress=None) -> AblationResult:
    """Execute the full factorial ablation and return the observation matrix.

    ``checkpoint_path`` appends every observation to a CSV as soon as it is
    produced. Against the deterministic backend this is unnecessary -- the whole
    campaign takes seconds. Against a paid hosted endpoint it is essential: a
    campaign is thousands of sequential billable calls, and a failure at 90%
    would otherwise discard both the results and the money already spent on
    them. The checkpoint is written with an fsync-free flush per row, which is
    ample for surviving a process crash.

    ``progress`` is an optional callable ``(done, total, observation)`` used to
    report advancement on long runs.
    """

    config = config or GMAISConfig()

    # Steps 1-2: prepare scenarios and load ground truth.
    corpus = generate_corpus(config.seed, config.scenarios_per_tier)
    gtkg = GroundTruthKnowledgeGraph(db_path)
    gtkg.load_corpus(corpus)

    # Step 3: fix the random seed for the whole campaign. The observation-noise
    # model draws from the seed directly rather than from global RNG state, so
    # thread scheduling in the concurrent Worker tier cannot perturb it.
    random.seed(config.seed)
    noise = NoiseModel.from_config(config)
    backend = build_backend(config.backend, seed=config.seed, model=config.model)
    orchestrator = GMAISOrchestrator(backend, config, noise=noise)

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

    checkpoint = _open_checkpoint(checkpoint_path)
    total = len(CELLS) * len(corpus)
    done = 0

    for cell in CELLS:
        for scenario in corpus:
            timings = ComponentTimings() if config.measure_wallclock else NullTimings()
            result = orchestrator.analyze(scenario, cell, timings=timings)
            rubric = gtkg.score(
                scenario,
                predicted_hypothesis=result.predicted_hypothesis,
                detected_injection_cids=result.detected_injection_cids,
                accepted_cids=[c.cid for c in scenario.claims],
                confidence=result.confidence,
            )
            audit_intact = 1 if (result.governance is None or result.governance.audit_intact) else 0

            gold_inj = set(result.gold_injection_cids)
            detected_set = set(result.detected_injection_cids)
            components = result.measured_components

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
                    n_detected=len(detected_set),
                    n_injected=len(gold_inj),
                    validator_iterations=result.validator_iterations,
                    audit_intact=audit_intact,
                    measured_latency_ms=result.measured_latency_ms,
                    measured_governance_ms=result.measured_governance_ms,
                    measured_worker_ms=components.get("measured_worker_tier_ms", 0.0),
                    measured_validator_ms=components.get("measured_validator_ms", 0.0),
                    measured_policy_ms=components.get("measured_policy_eval_ms", 0.0),
                    measured_audit_ms=components.get("measured_audit_record_ms", 0.0),
                    measured_redaction_ms=components.get("measured_redaction_ms", 0.0),
                    measured_queue_ms=components.get("measured_queue_ms", 0.0),
                    n_true_positive=len(gold_inj & detected_set),
                    n_false_positive=len(detected_set - gold_inj),
                    n_claims=len(scenario.claims),
                    governed_events=(
                        result.governance.events_total if result.governance else 0
                    ),
                    anchored_workers=result.anchored_workers,
                    peer_bias_exposure=result.peer_bias_exposure,
                    entities_redacted=result.entities_redacted,
                )
            )

            done += 1
            if checkpoint is not None:
                _write_checkpoint(checkpoint, observations[-1])
            if progress is not None:
                progress(done, total, observations[-1])

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
            "mean_measured_latency_ms": round(
                sum(o.measured_latency_ms for o in observations if o.cell == name) / b["n"], 4
            ) if b["n"] else 0.0,
            "mean_measured_governance_ms": round(
                sum(o.measured_governance_ms for o in observations if o.cell == name) / b["n"], 4
            ) if b["n"] else 0.0,
            "mean_anchored_workers": round(
                sum(o.anchored_workers for o in observations if o.cell == name) / b["n"], 4
            ) if b["n"] else 0.0,
            "mean_peer_bias_exposure": round(
                sum(o.peer_bias_exposure for o in observations if o.cell == name) / b["n"], 3
            ) if b["n"] else 0.0,
        }

    if checkpoint is not None:
        checkpoint["handle"].close()

    corpus_stats = {
        **gtkg.stats(),
        "scenarios_per_tier": config.scenarios_per_tier,
        "claims_per_tier": {
            tier: sum(len(s.claims) for s in corpus if s.tier == tier)
            for tier in sorted({s.tier for s in corpus})
        },
        "injected_per_tier": {
            tier: sum(s.n_injected for s in corpus if s.tier == tier)
            for tier in sorted({s.tier for s in corpus})
        },
        "tolerance_conformance": _tolerance_conformance(corpus),
    }

    gtkg.close()
    return AblationResult(
        config=config,
        observations=observations,
        security_tax=sec_tax,
        per_cell_metrics=per_cell_metrics,
        environment=environment_manifest() if config.measure_wallclock else {},
        noise_manifest={
            **noise.manifest(),
            "realised": noise.corpus_diagnostics(corpus),
        },
        corpus_stats=corpus_stats,
    )


def _open_checkpoint(path: str | None):
    """Open an incremental observation CSV, or return None if not requested."""

    if not path:
        return None
    import csv
    import os

    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    handle = open(path, "w", newline="", encoding="utf-8")
    return {"handle": handle, "writer": None, "csv": csv}


def _write_checkpoint(checkpoint, observation: Observation) -> None:
    """Append one observation and flush, so a crash loses at most the last row."""

    row = asdict(observation)
    if checkpoint["writer"] is None:
        checkpoint["writer"] = checkpoint["csv"].DictWriter(
            checkpoint["handle"], fieldnames=list(row.keys())
        )
        checkpoint["writer"].writeheader()
    checkpoint["writer"].writerow(row)
    checkpoint["handle"].flush()


def _tolerance_conformance(corpus) -> Dict[str, float]:
    """Fraction of the corpus inside each pre-registered Section 3.2.2 tolerance.

    Reported so a reviewer can verify the complexity stratification actually
    held, rather than taking the design on trust.
    """

    from .scenarios import within_tolerance

    if not corpus:
        return {}
    checks = [within_tolerance(s) for s in corpus]
    return {
        key: round(sum(1 for c in checks if c[key]) / len(checks), 4)
        for key in checks[0]
    }
