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
from .governance.tokens import issue_token
from .llm.base import LLMBackend
from .scenarios import Scenario


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
    latency_ms: float
    tokens: int
    governance: Optional[GovernanceReport] = None
    validator_iterations: int = 0


class GMAISOrchestrator:
    """Wires Worker tier, Validator and Governance Layer for a given cell."""

    def __init__(self, backend: LLMBackend, config: GMAISConfig):
        self.config = config
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
            )
            gov.mediate(event)

    def analyze(self, scenario: Scenario, cell: FactorialCell) -> AnalysisResult:
        worker_output = self.workers.run(scenario)

        latency = worker_output.latency_ms
        tokens = worker_output.tokens
        all_messages: List[tuple[str, List[Message]]] = [("worker", worker_output.messages)]

        if cell.validation:
            validation = self.validator.validate(scenario, worker_output)
            predicted = validation.predicted_hypothesis
            detected = validation.detected_injection_cids
            confidence = validation.confidence
            latency += validation.latency_ms
            tokens += validation.tokens
            iterations = validation.iterations
            all_messages.append(("validator", validation.messages))
        else:
            # No validator: accept the Worker tier's unverified synthesis.
            predicted = worker_output.predicted_hypothesis
            detected = []
            confidence = 0.5
            iterations = 0

        governance_report: Optional[GovernanceReport] = None
        if cell.governance:
            gov = GovernanceLayer(
                theta_policy=self.config.theta_policy,
                sensitivity_threshold=self.config.sensitivity_threshold,
                secret=self.config.delegation_secret,
                saturation_margin=self.config.queue_saturation_margin,
            )
            for sender, messages in all_messages:
                self._mediate(gov, sender, messages)
            governance_report = gov.finalise()
            latency += governance_report.overhead_latency_ms
            tokens += governance_report.overhead_tokens

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
            governance=governance_report,
            validator_iterations=iterations,
        )
