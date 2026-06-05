"""Authenticated delegation tokens (Section 2.3.4, Chan et al. 2025).

Authenticated delegation is the verifiable, scope-limited transfer of operating
authority to an agent. Each agent carries a token binding its identity, its
authorised scope and its classification clearance, signed with an HMAC so that
the Governance Layer can verify provenance before honouring any inter-agent
message. Tokens are intentionally lightweight: the thesis targets a Minimum
Viable Architecture, not a production PKI.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass, field

from ..config import CLASSIFICATION_LEVELS


def _clearance_index(level: str) -> int:
    try:
        return CLASSIFICATION_LEVELS.index(level)
    except ValueError as exc:
        raise ValueError(f"Unknown classification level: {level!r}") from exc


@dataclass
class DelegationToken:
    """A signed, scope-limited grant of authority to an agent."""

    agent_id: str
    scope: str  # e.g. "analyse", "validate", "synthesise"
    clearance: str  # one of CLASSIFICATION_LEVELS
    issued_at: float = field(default_factory=time.time)
    signature: str = ""

    def payload(self) -> str:
        return f"{self.agent_id}|{self.scope}|{self.clearance}|{self.issued_at}"

    def sign(self, secret: str) -> "DelegationToken":
        self.signature = hmac.new(
            secret.encode(), self.payload().encode(), hashlib.sha256
        ).hexdigest()
        return self

    def verify(self, secret: str) -> bool:
        expected = hmac.new(
            secret.encode(), self.payload().encode(), hashlib.sha256
        ).hexdigest()
        return bool(self.signature) and hmac.compare_digest(expected, self.signature)

    @property
    def clearance_level(self) -> int:
        return _clearance_index(self.clearance)


def issue_token(agent_id: str, scope: str, clearance: str, secret: str) -> DelegationToken:
    """Mint and sign a delegation token for an agent."""

    return DelegationToken(agent_id=agent_id, scope=scope, clearance=clearance).sign(secret)
