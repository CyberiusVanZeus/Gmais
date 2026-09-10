"""Communication events and the governance evaluation function fG(e).

Section 3.3.1 defines the multi-agent system as M = <A, S, E, G, P>, where each
communication event e = <m, t, c> is a message payload m at timestamp t with
token context c. The Governance Layer applies a probabilistic evaluation
function fG(e): a message is accepted (fG = 1) only when three criteria hold
simultaneously --

  1. authenticated delegation token verifies,
  2. need-to-know classification clearance is satisfied,
  3. the information-sensitivity threshold is respected,

at a calibrated compliance probability P(compliance | e) >= theta_policy
(Eq. 3.1). Failing messages (fG = 0) are logged and redacted rather than
dropped, preserving audit-trail continuity (South et al., 2025).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional

from ..config import CLASSIFICATION_LEVELS
from .redaction import redact_entities
from .tokens import DelegationToken, _clearance_index


@dataclass
class Event:
    """A directed inter-agent communication event e = <m, t, c>."""

    sender: str
    recipient: str
    message: str  # payload m
    classification: str = "UNCLASSIFIED"  # sensitivity of the payload
    sensitivity: float = 0.0  # information-sensitivity score in [0, 1]
    token: Optional[DelegationToken] = None  # token context c
    recipient_clearance: str = "SECRET"
    timestamp: float = field(default_factory=time.time)
    # Worker-to-worker peer exchange triggers named-entity redaction.
    peer: bool = False
    entities: List[str] = field(default_factory=list)

    @property
    def context_tokens(self) -> int:
        """Extra token budget carried by governance metadata (context c).

        Governed messages carry delegation and classification context, which is
        the channel through which the Governance Layer increases token
        consumption (H2): more bytes on the wire per inter-agent message.
        """

        return 12  # delegation id + classification tag + policy nonce


@dataclass
class PolicyDecision:
    """Result of evaluating fG(e)."""

    accepted: int  # fG(e) in {0, 1}
    compliance: float  # P(compliance | e)
    reason: str
    redacted_message: str
    entities_redacted: int = 0  # named-entity mentions stripped (peer NTK)
    #: Measured wall-clock nanoseconds spent inside named-entity redaction, so
    #: the Governance Layer can cost redaction separately from the fG(e)
    #: decision that encloses it (Section 3.3.4).
    redaction_ns: int = 0


class PolicyEngine:
    """Implements fG(e) over the policy-constraint set P."""

    def __init__(self, *, theta_policy: float, sensitivity_threshold: float, secret: str):
        self.theta_policy = theta_policy
        self.sensitivity_threshold = sensitivity_threshold
        self.secret = secret

    def _need_to_know_ok(self, event: Event) -> bool:
        required = _clearance_index(event.classification)
        held = _clearance_index(event.recipient_clearance)
        return held >= required

    def evaluate(self, event: Event) -> PolicyDecision:
        token_ok = event.token is not None and event.token.verify(self.secret)
        ntk_ok = self._need_to_know_ok(event)
        sensitivity_ok = event.sensitivity <= self.sensitivity_threshold

        # Calibrated compliance probability: a weighted blend of the three hard
        # checks. All three must hold for compliance to clear theta_policy.
        compliance = (
            0.34 * float(token_ok)
            + 0.33 * float(ntk_ok)
            + 0.33 * float(sensitivity_ok)
        )
        accepted = int(compliance >= self.theta_policy and token_ok and ntk_ok and sensitivity_ok)

        entities_redacted = 0
        redaction_ns = 0
        if accepted:
            redacted = event.message
            reason = "compliant"
            # Need-to-know on worker-to-worker exchange: strip named entities so
            # peers reason over the substance, not the actor identity (bias
            # control). The message is authorised; only entity labels are masked.
            if event.peer:
                _t0 = time.perf_counter_ns()
                redacted, entities_redacted, _ = redact_entities(
                    event.message, event.entities
                )
                redaction_ns = time.perf_counter_ns() - _t0
                reason = (
                    f"compliant:entity-redacted({entities_redacted})"
                    if entities_redacted
                    else "compliant:peer"
                )
        else:
            failed = []
            if not token_ok:
                failed.append("delegation")
            if not ntk_ok:
                failed.append("need-to-know")
            if not sensitivity_ok:
                failed.append("sensitivity")
            reason = "redacted:" + "+".join(failed)
            redacted = "[REDACTED BY GOVERNANCE LAYER]"

        return PolicyDecision(
            accepted=accepted,
            compliance=round(compliance, 4),
            reason=reason,
            redacted_message=redacted,
            entities_redacted=entities_redacted,
            redaction_ns=redaction_ns,
        )
