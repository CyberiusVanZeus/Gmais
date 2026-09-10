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

from ..timing import ComponentTimings, NullTimings
from .audit import AuditLog
from .policy import Event, PolicyEngine
from .queue import MediationQueue

# Modelled per-event policy-evaluation latency (ms) and the extra latency a
# rate-limited (serialised) event incurs.
#
# These constants are the *deployment* cost model: in a distributed deployment
# the dominant governance cost is the network hop to a policy decision point and
# the durable append of the audit record, neither of which an in-process
# reference implementation incurs. They are carried in
# ``overhead_latency_ms`` and feed the modelled Security Tax.
#
# Separately, ``GovernanceReport.measured_*`` reports the *actual* wall-clock
# cost of the mediation work this implementation performs -- HMAC verification,
# fG(e) evaluation, SHA-256 chain append, entity redaction, queue bookkeeping --
# measured with time.perf_counter_ns. The two must never be conflated, and the
# results package reports them in separate tables.
POLICY_EVAL_MS = 3.5
SERIALISATION_PENALTY_MS = 6.0


@dataclass
class GovernanceReport:
    """Telemetry produced by mediating one scenario's message traffic."""

    events_total: int = 0
    events_accepted: int = 0
    events_redacted: int = 0
    peer_events: int = 0  # worker-to-worker exchanges mediated
    entities_redacted: int = 0  # named-entity mentions stripped on peer NTK
    overhead_latency_ms: float = 0.0  # modelled deployment cost
    overhead_tokens: int = 0
    #: Measured wall-clock cost of the mediation actually executed (ms).
    measured_overhead_ms: float = 0.0
    measured_policy_ms: float = 0.0
    measured_audit_ms: float = 0.0
    measured_redaction_ms: float = 0.0
    measured_queue_ms: float = 0.0
    audit_intact: bool = True
    audit_length: int = 0
    serialisation_ratio: float = 0.0
    max_queue_depth: int = 0
    redacted_messages: List[str] = field(default_factory=list)
    # An illustrative before/after pair for the web UI (first peer event).
    sample_peer_before: str = ""
    sample_peer_after: str = ""


class GovernanceLayer:
    """Centralised governance mediation over inter-agent events."""

    def __init__(self, *, theta_policy: float, sensitivity_threshold: float,
                 secret: str, saturation_margin: float = 0.15,
                 timings: ComponentTimings | None = None) -> None:
        self.policy = PolicyEngine(
            theta_policy=theta_policy,
            sensitivity_threshold=sensitivity_threshold,
            secret=secret,
        )
        self.audit = AuditLog()
        self.queue = MediationQueue(saturation_margin=saturation_margin)
        self.report = GovernanceReport()
        self.timings = timings or NullTimings()

    def mediate(self, event: Event) -> bool:
        """Mediate one event. Returns True if the message is accepted (fG=1).

        Every stage is timed independently so the governance overhead can be
        attributed to policy evaluation, audit-chain construction, entity
        redaction and queue bookkeeping rather than reported as a lump sum.
        """

        t = self.timings
        with t.measure("governance_total"):
            with t.measure("queue"):
                rate_limited = self.queue.enqueue()
            # ``PolicyEngine.evaluate`` performs entity redaction inline for peer
            # events; it reports the time spent there so redaction can be costed
            # separately from the policy decision itself.
            with t.measure("policy_eval"):
                decision = self.policy.evaluate(event)
            t.reattribute("policy_eval", "redaction", decision.redaction_ns)
            with t.measure("audit_record"):
                self.audit.record(
                    sender=event.sender,
                    recipient=event.recipient,
                    decision=decision.accepted,
                    reason=decision.reason,
                    message=decision.redacted_message,
                )
            with t.measure("queue"):
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

        # Need-to-know entity redaction on worker-to-worker exchange.
        if event.peer:
            self.report.peer_events += 1
            self.report.entities_redacted += decision.entities_redacted
            if not self.report.sample_peer_before and decision.entities_redacted:
                self.report.sample_peer_before = event.message
                self.report.sample_peer_after = decision.redacted_message
        return bool(decision.accepted)

    def finalise(self) -> GovernanceReport:
        # Chain verification is itself a governance cost and is charged as one,
        # to both the audit component and the end-to-end governance total.
        with self.timings.measure("governance_total"):
            with self.timings.measure("audit_record"):
                self.report.audit_intact = self.audit.verify_integrity()
        self.report.audit_length = len(self.audit)

        t = self.timings
        self.report.measured_overhead_ms = round(t.ms("governance_total"), 6)
        self.report.measured_policy_ms = round(t.ms("policy_eval"), 6)
        self.report.measured_audit_ms = round(t.ms("audit_record"), 6)
        self.report.measured_redaction_ms = round(t.ms("redaction"), 6)
        self.report.measured_queue_ms = round(t.ms("queue"), 6)

        self.report.serialisation_ratio = self.queue.metrics.serialisation_ratio
        self.report.max_queue_depth = self.queue.metrics.max_depth
        self.report.overhead_latency_ms = round(self.report.overhead_latency_ms, 3)
        return self.report
