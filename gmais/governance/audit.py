"""Hash-chained audit log.

End-to-end auditability is the property the thesis argues mainstream multi-agent
frameworks lack (Section 1.1). The Governance Layer records every mediated event
in an append-only log where each entry commits to the previous entry's hash via
SHA-256, forming a tamper-evident chain. Cycle 3 convergence requires audit logs
to "maintain cryptographic integrity across the full execution sequence"
(Section 3.1.4); :meth:`AuditLog.verify_integrity` is the check that enforces it.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import List

GENESIS_HASH = "0" * 64


@dataclass
class AuditEntry:
    """One link in the audit chain."""

    index: int
    timestamp: float
    sender: str
    recipient: str
    decision: int  # fG(e)
    reason: str
    message_digest: str  # hash of the (possibly redacted) payload
    prev_hash: str
    entry_hash: str = ""

    def compute_hash(self) -> str:
        body = json.dumps(
            {
                "index": self.index,
                "timestamp": self.timestamp,
                "sender": self.sender,
                "recipient": self.recipient,
                "decision": self.decision,
                "reason": self.reason,
                "message_digest": self.message_digest,
                "prev_hash": self.prev_hash,
            },
            sort_keys=True,
        )
        return hashlib.sha256(body.encode()).hexdigest()


class AuditLog:
    """Append-only, hash-chained record of governance decisions."""

    def __init__(self) -> None:
        self._entries: List[AuditEntry] = []

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def entries(self) -> List[AuditEntry]:
        return list(self._entries)

    @property
    def head_hash(self) -> str:
        return self._entries[-1].entry_hash if self._entries else GENESIS_HASH

    def record(self, *, sender: str, recipient: str, decision: int,
               reason: str, message: str) -> AuditEntry:
        message_digest = hashlib.sha256(message.encode()).hexdigest()
        entry = AuditEntry(
            index=len(self._entries),
            timestamp=time.time(),
            sender=sender,
            recipient=recipient,
            decision=decision,
            reason=reason,
            message_digest=message_digest,
            prev_hash=self.head_hash,
        )
        entry.entry_hash = entry.compute_hash()
        self._entries.append(entry)
        return entry

    def verify_integrity(self) -> bool:
        """Return True iff the chain is internally consistent (untampered)."""

        prev = GENESIS_HASH
        for entry in self._entries:
            if entry.prev_hash != prev:
                return False
            if entry.compute_hash() != entry.entry_hash:
                return False
            prev = entry.entry_hash
        return True

    def rejected_count(self) -> int:
        return sum(1 for e in self._entries if e.decision == 0)
