"""The Governance Layer (G in M = <A, S, E, G, P>).

This is the unified mediation component commissioned in formative DSR Cycle 3
(Section 3.1.4). It sits between agents and intercepts every inter-agent
message, applying the policy function fG(e), recording a tamper-evident audit
entry, tracking queue metrics, and accounting the latency and token overhead
that constitute the governance side of the Security Tax (H2).

The overhead model is deliberately explicit so it can be audited:

* each mediated event costs ``policy_eval_ms`` of latency plus a serialisation
  penalty when the queue rate-limits, and
* each mediated event adds ``context_tokens`` of metadata to token consumption.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .audit import AuditLog
from .policy import Event, PolicyEngine
from .queue import MediationQueue

# Fixed per-event policy-evaluation latency (ms) and the extra latency a
# rate-limited (serialised) event incurs.
POLICY_EVAL_MS = 3.5
SERIALISATION_PENALTY_MS = 6.0


@dataclass
class GovernanceReport:
    """Telemetry produced by mediating one scenario's message traffic."""

    events_total: int = 0
    events_accepted: int = 0
    events_redacted: int = 0
    overhead_latency_ms: float = 0.0
    overhead_tokens: int = 0
    audit_intact: bool = True
    audit_length: int = 0
    serialisation_ratio: float = 0.0
    max_queue_depth: int = 0
    redacted_messages: List[str] = field(default_factory=list)


class GovernanceLayer:
    """Centralised governance mediation over inter-agent events."""

    def __init__(self, *, theta_policy: float, sensitivity_threshold: float,
                 secret: str, saturation_margin: float = 0.15) -> None:
        self.policy = PolicyEngine(
            theta_policy=theta_policy,
            sensitivity_threshold=sensitivity_threshold,
            secret=secret,
        )
        self.audit = AuditLog()
        self.queue = MediationQueue(saturation_margin=saturation_margin)
        self.report = GovernanceReport()

    def mediate(self, event: Event) -> bool:
        """Mediate one event. Returns True if the message is accepted (fG=1)."""

        rate_limited = self.queue.enqueue()
        decision = self.policy.evaluate(event)
        self.audit.record(
            sender=event.sender,
            recipient=event.recipient,
            decision=decision.accepted,
            reason=decision.reason,
            message=decision.redacted_message,
        )
        self.queue.dequeue()

        # Account overhead.
        self.report.events_total += 1
        latency = POLICY_EVAL_MS + (SERIALISATION_PENALTY_MS if rate_limited else 0.0)
        self.report.overhead_latency_ms += latency
        self.report.overhead_tokens += event.context_tokens
        if decision.accepted:
            self.report.events_accepted += 1
        else:
            self.report.events_redacted += 1
            self.report.redacted_messages.append(event.message)
        return bool(decision.accepted)

    def finalise(self) -> GovernanceReport:
        self.report.audit_intact = self.audit.verify_integrity()
        self.report.audit_length = len(self.audit)
        self.report.serialisation_ratio = self.queue.metrics.serialisation_ratio
        self.report.max_queue_depth = self.queue.metrics.max_depth
        self.report.overhead_latency_ms = round(self.report.overhead_latency_ms, 3)
        return self.report
