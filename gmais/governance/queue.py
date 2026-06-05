"""Asynchronous mediation queue instrumentation.

Section 3.3.1 specifies that the Governance Layer operates via asynchronous
event queues rather than synchronous interception, "maintaining sequential
auditability without invalidating concurrency claims," and that queue depth,
message-serialisation ratios and throughput-decay curves are logged to validate
the asynchronous-mediation assumption. This module records those queue metrics
as events are mediated, and implements the pre-registered adaptive rate-limit
trigger (backlog exceeding steady-state depth by ``queue_saturation_margin``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class QueueMetrics:
    """Observed queue behaviour over a mediation episode."""

    depth_samples: List[int] = field(default_factory=list)
    serialised: int = 0  # messages that had to serialise (rate-limited)
    enqueued: int = 0
    dequeued: int = 0

    @property
    def max_depth(self) -> int:
        return max(self.depth_samples) if self.depth_samples else 0

    @property
    def steady_state_depth(self) -> float:
        if not self.depth_samples:
            return 0.0
        return round(sum(self.depth_samples) / len(self.depth_samples), 3)

    @property
    def serialisation_ratio(self) -> float:
        if self.enqueued == 0:
            return 0.0
        return round(self.serialised / self.enqueued, 4)


class MediationQueue:
    """A minimal instrumented FIFO modelling asynchronous governance mediation."""

    def __init__(self, saturation_margin: float = 0.15) -> None:
        self.saturation_margin = saturation_margin
        self.metrics = QueueMetrics()
        self._depth = 0
        self._running_mean = 0.0

    def enqueue(self) -> bool:
        """Enqueue an event. Returns True if adaptive rate-limiting triggered."""

        self._depth += 1
        self.metrics.enqueued += 1
        self.metrics.depth_samples.append(self._depth)

        # Update running steady-state estimate and test the saturation trigger.
        n = self.metrics.enqueued
        self._running_mean += (self._depth - self._running_mean) / n
        threshold = self._running_mean * (1.0 + self.saturation_margin)
        rate_limited = self._depth > max(1.0, threshold)
        if rate_limited:
            self.metrics.serialised += 1
        return rate_limited

    def dequeue(self) -> None:
        if self._depth > 0:
            self._depth -= 1
            self.metrics.dequeued += 1
