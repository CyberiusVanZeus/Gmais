"""GMAIS orchestrator.

The Orchestrator occupies the apex of the web-of-intelligence topology
(Section 2.1, Figure 2.2): it ingests a normalised scenario, drives the
concurrent Worker tier, optionally invokes the Validator, optionally routes all
inter-agent traffic through the Governance Layer, and emits a single graded
analytical product with full latency/token telemetry.

The same orchestrator runs all four factorial cells; the cell's
``validation``/``governance`` flags decide which mechanisms are active, so the
ablation contrast is a pure function of configuration rather than of code paths
that differ between conditions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .agents.validator import ValidatorAgent
from .agents.worker import Message, WorkerTier
from .config import FactorialCell, GMAISConfig
from .governance.layer import GovernanceLayer, GovernanceReport
from .governance.policy import Event
from .governance.redaction import redact_entities
from .governance.tokens import issue_token
from .llm.base import LLMBackend
from .noise import NoiseModel
from .scenarios import Scenario
from .timing import ComponentTimings, NullTimings


@dataclass
class AnalysisResult:
    """The orchestrator's product for one (scenario, cell) observation."""

    scenario_id: str
    cell: str
    predicted_hypothesis: str
    gold_hypothesis: str
    correct: bool
    detected_injection_cids: List[str]
    gold_injection_cids: List[str]
    confidence: float
    #: Modelled end-to-end latency: inference cost model + deployment governance
    #: cost model. See :mod:`gmais.timing` for why this is kept distinct from the
    #: measured figures below.
    latency_ms: float
    tokens: int
    #: Measured wall-clock latency of the work this implementation executed.
    measured_latency_ms: float = 0.0
    measured_governance_ms: float = 0.0
    #: Per-component measured breakdown (``measured_<component>_ms``).
    measured_components: dict = field(default_factory=dict)
    governance: Optional[GovernanceReport] = None
    validator_iterations: int = 0
    # Worker-to-worker bias control: named-entity mentions still visible to
    # peers after mediation (0 under governance; full exposure without it).
    peer_bias_exposure: int = 0
    entities_redacted: int = 0
    # Workers that herded onto the entity-anchored hypothesis during unmediated
    # peer exchange (structurally zero under governance).
    anchored_workers: int = 0
    # Verified-source corroboration count from the Validator's web search.
    verified_corroboration: int = 0


class GMAISOrchestrator:
    """Wires Worker tier, Validator and Governance Layer for a given cell."""

    def __init__(self, backend: LLMBackend, config: GMAISConfig,
                 noise: NoiseModel | None = None):
        self.config = config
        # The observation-noise model is shared across every cell so that the
        # ablation contrast stays a pure function of configuration (see
        # :mod:`gmais.noise` for the determinism contract).
        self.noise = noise if noise is not None else NoiseModel.from_config(config)
        self.workers = WorkerTier(
            backend, n_workers=config.n_workers, temperature=config.worker_temperature
        )
        self.validator = ValidatorAgent(
            backend,
            temperature=config.validator_temperature,
            ci_width_threshold=config.ci_width_threshold,
            convergence_threshold=config.convergence_threshold,
            max_iterations=config.max_critique_iterations,
        )
        # Pre-mint delegation tokens for the agents (authenticated delegation).
        secret = config.delegation_secret
        self._tokens = {
            "worker": issue_token("worker", "analyse", "SECRET", secret),
            "validator": issue_token("validator", "validate", "SECRET", secret),
        }

    def _mediate(self, gov: GovernanceLayer, sender: str, messages: List[Message]) -> None:
        token = self._tokens.get(sender, self._tokens["worker"])
        for m in messages:
            event = Event(
                sender=sender,
                recipient=m.recipient,
                message=m.payload,
                classification=m.classification,
                sensitivity=m.sensitivity,
                token=token,
                recipient_clearance="SECRET",
                peer=m.peer,
                entities=list(m.entities),
            )
            gov.mediate(event)

    def analyze(self, scenario: Scenario, cell: FactorialCell,
                activity=None, web_search=None,
                timings: ComponentTimings | None = None) -> AnalysisResult:
        # ``activity`` emits to the live operational feed; ``web_search`` is the
        # Validator's verified-source corroboration client (both optional).
        emit = activity or (lambda *a, **k: None)
        timings = timings if timings is not None else (
            ComponentTimings() if self.config.measure_wallclock else NullTimings()
        )
        emit("ingest", f"Ingesting {scenario.sid} [{cell.name}] - {scenario.tier} tier, "
             f"{len(scenario.claims)} claims, {scenario.n_injected} injected")

        # Whether peer traffic will be entity-redacted is a property of the cell,
        # and the Worker tier needs it up front: redaction is what removes the
        # anchoring cue from worker-to-worker exchange (Section 3.3.1).
        worker_output = self.workers.run(
            scenario,
            peer_redaction=cell.governance,
            noise=self.noise,
            timings=timings,
            activity=activity,
        )

        latency = worker_output.latency_ms
        tokens = worker_output.tokens
        all_messages: List[tuple[str, List[Message]]] = [
            ("worker", worker_output.messages),
            ("worker", worker_output.peer_messages),  # worker-to-worker exchange
        ]

        # Total named-entity mentions circulating in worker-to-worker peer
        # traffic before any mediation (the maximum bias exposure).
        total_peer_mentions = sum(
            redact_entities(m.payload, m.entities)[1]
            for m in worker_output.peer_messages
        )

        verified_corroboration = 0
        if cell.validation:
            validation = self.validator.validate(
                scenario, worker_output, activity=activity, web_search=web_search,
                noise=self.noise, timings=timings,
            )
            predicted = validation.predicted_hypothesis
            detected = validation.detected_injection_cids
            confidence = validation.confidence
            latency += validation.latency_ms
            tokens += validation.tokens
            iterations = validation.iterations
            verified_corroboration = validation.verified_corroboration
            all_messages.append(("validator", validation.messages))
        else:
            # No validator: accept the Worker tier's unverified synthesis.
            emit("validator", "Validation disabled for this cell - accepting "
                 "unverified Worker synthesis", status="done")
            predicted = worker_output.predicted_hypothesis
            detected = []
            confidence = 0.5
            iterations = 0

        governance_report: Optional[GovernanceReport] = None
        if cell.governance:
            n_events = sum(len(m) for _, m in all_messages)
            emit("governance", f"Governance Layer mediating {n_events} inter-agent "
                 "event(s): fG(e) policy, need-to-know, audit")
            gov = GovernanceLayer(
                theta_policy=self.config.theta_policy,
                sensitivity_threshold=self.config.sensitivity_threshold,
                secret=self.config.delegation_secret,
                saturation_margin=self.config.queue_saturation_margin,
                timings=timings,
            )
            for sender, messages in all_messages:
                self._mediate(gov, sender, messages)
            governance_report = gov.finalise()
            latency += governance_report.overhead_latency_ms
            tokens += governance_report.overhead_tokens
            entities_redacted = governance_report.entities_redacted
            emit("governance", f"Mediation complete: {governance_report.events_redacted} "
                 f"redacted, {entities_redacted} entity mention(s) masked, audit "
                 f"chain {'intact' if governance_report.audit_intact else 'BROKEN'}",
                 status="done")
        else:
            # Ungoverned: peer entity names circulate unredacted -> full bias.
            entities_redacted = 0

        # Bias exposure = entity mentions a worker still sees from peers.
        peer_bias_exposure = total_peer_mentions - entities_redacted

        emit("score", f"Grading {scenario.sid} [{cell.name}] against the GTKG rubric",
             status="done", correct=(predicted == scenario.gold_hypothesis))

        # Measured wall clock: the Worker tier's critical path plus whatever
        # validation and governance actually executed. Inference time is excluded
        # here by construction -- it lives in ``latency_ms``.
        measured_total = (
            timings.ms("worker_tier") + timings.ms("validator")
            + timings.ms("governance_total")
        )

        return AnalysisResult(
            scenario_id=scenario.sid,
            cell=cell.name,
            predicted_hypothesis=predicted,
            gold_hypothesis=scenario.gold_hypothesis,
            correct=(predicted == scenario.gold_hypothesis),
            detected_injection_cids=detected,
            gold_injection_cids=scenario.injected_cids,
            confidence=confidence,
            latency_ms=round(latency, 3),
            tokens=tokens,
            measured_latency_ms=round(measured_total, 6),
            measured_governance_ms=round(timings.ms("governance_total"), 6),
            measured_components=timings.as_dict(),
            governance=governance_report,
            validator_iterations=iterations,
            peer_bias_exposure=peer_bias_exposure,
            entities_redacted=entities_redacted,
            anchored_workers=worker_output.anchored_workers,
            verified_corroboration=verified_corroboration,
        )
