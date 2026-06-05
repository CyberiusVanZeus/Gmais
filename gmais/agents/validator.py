"""Validator Agent.

The Validator is the structural expression of the thesis's central theoretical
commitment: cognitive scaffolding must be embedded as an algorithmic constraint,
not bolted on as a terminal filter (Section 2.3.6). It runs cold (T=0.2) and:

1. grades every source with the Admiralty Code on two independent axes,
2. discards claims whose Admiralty confidence falls below a reliability floor,
   flagging adversarially weak claims as detected injections,
3. runs Analysis of Competing Hypotheses over the surviving evidence, and
4. iterates a critique loop under the bounded-rationality stopping rule
   (halt when ACH convergence >= 0.85 or the confidence-interval width < 0.15,
   Section 2.1 / config), so validation cannot loop indefinitely.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from ..ach import ACHMatrix, ACHResult, CONSISTENT, Evidence, INCONSISTENT, NEUTRAL
from ..admiralty import AdmiraltyGrade, grade_source
from ..llm.base import LLMBackend
from ..scenarios import Scenario
from .worker import Message, WorkerOutput

# Claims graded below this Admiralty confidence are rejected as unreliable.
RELIABILITY_FLOOR = 0.40


@dataclass
class ValidationResult:
    """Validated analytical product."""

    predicted_hypothesis: str
    detected_injection_cids: List[str]
    accepted_cids: List[str]
    grades: Dict[str, AdmiraltyGrade]
    confidence: float
    ci_width: float
    ach: ACHResult
    iterations: int
    messages: List[Message] = field(default_factory=list)
    latency_ms: float = 0.0
    tokens: int = 0


class ValidatorAgent:
    """Source-reliability + ACH validation with bounded-rationality control."""

    def __init__(self, backend: LLMBackend, *, temperature: float,
                 ci_width_threshold: float, convergence_threshold: float,
                 max_iterations: int):
        self.backend = backend
        self.temperature = temperature
        self.ci_width_threshold = ci_width_threshold
        self.convergence_threshold = convergence_threshold
        self.max_iterations = max_iterations

    def _build_ach(self, scenario: Scenario, surviving) -> ACHMatrix:
        matrix = ACHMatrix(scenario.hypotheses)
        for c in surviving:
            grade = grade_source(c.source)
            consistency = {}
            for h in scenario.hypotheses:
                if h == c.supports:
                    consistency[h] = CONSISTENT
                elif c.supports and h != c.supports:
                    consistency[h] = INCONSISTENT
                else:
                    consistency[h] = NEUTRAL
            matrix.add_evidence(
                Evidence(eid=c.cid, text=c.text, weight=grade.confidence,
                         consistency=consistency)
            )
        return matrix

    def validate(self, scenario: Scenario, worker_output: WorkerOutput) -> ValidationResult:
        grades: Dict[str, AdmiraltyGrade] = {}
        surviving = []
        detected: List[str] = []

        # Step 1-2: Admiralty grading and reliability-floor filtering.
        for c in scenario.claims:
            grade = grade_source(c.source)
            grades[c.cid] = grade
            if grade.confidence < RELIABILITY_FLOOR:
                detected.append(c.cid)  # flagged as adversarial/unreliable
            else:
                surviving.append(c)

        # Steps 3-4: ACH under the bounded-rationality critique loop.
        latency = 0.0
        tokens = 0
        iterations = 0
        ach_result = None
        confidence = 0.0
        ci_width = 1.0
        critique_messages: List[Message] = []
        while iterations < self.max_iterations:
            iterations += 1
            prompt = (
                f"Validator critique iteration {iterations} for {scenario.sid}.\n"
                f"Surviving evidence: {[c.cid for c in surviving]}\n"
                "Apply Admiralty grading and ACH diagnosticity; assess calibration."
            )
            resp = self.backend.generate(
                prompt, temperature=self.temperature, role="validator", max_tokens=320
            )
            latency += resp.latency_ms
            tokens += resp.total_tokens

            # Each critique round is an inter-agent event the Governance Layer
            # mediates (critique/correction/verification loop, Section 3.1.4).
            critique_messages.append(
                Message(
                    recipient="worker",
                    payload=f"critique:{scenario.sid}:iter={iterations}",
                    classification="OFFICIAL",
                    sensitivity=0.2,
                )
            )

            ach_result = self._build_ach(scenario, surviving).evaluate()
            convergence = ach_result.convergence
            # CI width shrinks as convergence rises and evidence accumulates.
            ci_width = round(max(0.0, (1.0 - convergence) * 0.6), 4)
            confidence = round(0.5 + 0.5 * convergence, 4)

            if convergence >= self.convergence_threshold or ci_width < self.ci_width_threshold:
                break  # bounded-rationality satisficing halt

        predicted = ach_result.selected if ach_result else worker_output.predicted_hypothesis

        messages = critique_messages + [
            Message(
                recipient="orchestrator",
                payload=f"validated:{scenario.sid}:H={predicted}:conf={confidence}",
                classification="OFFICIAL",
                sensitivity=0.25,
            ),
            Message(
                recipient="audit",
                payload=f"injections_detected:{scenario.sid}:{detected}",
                classification="CONFIDENTIAL",
                sensitivity=0.3,
            ),
        ]

        return ValidationResult(
            predicted_hypothesis=predicted,
            detected_injection_cids=detected,
            accepted_cids=[c.cid for c in surviving],
            grades=grades,
            confidence=confidence,
            ci_width=ci_width,
            ach=ach_result,
            iterations=iterations,
            messages=messages,
            latency_ms=round(latency, 3),
            tokens=tokens,
        )
