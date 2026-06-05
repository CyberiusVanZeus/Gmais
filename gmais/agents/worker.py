"""Worker Agent tier.

The Worker tier is the middle layer of the two-tier MVA (Section 3.3.1). Workers
execute *concurrently* to preserve the non-linear analytical throughput the
web-of-intelligence model demands, each producing candidate hypotheses, source
assessments and synthesis fragments at an elevated temperature (T=0.7) for
exploratory coverage. Critically, the Worker tier performs *no* source
validation of its own: absent the Validator, it accepts every sourced claim at
face value, which is exactly the failure mode (unverified reasoning traces) that
the validation factor is designed to remediate.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Dict, List

from ..llm.base import LLMBackend
from ..scenarios import Scenario


@dataclass
class Message:
    """A lightweight inter-agent message the orchestrator wraps as an Event."""

    recipient: str
    payload: str
    classification: str = "UNCLASSIFIED"
    sensitivity: float = 0.1


@dataclass
class WorkerOutput:
    """Aggregated product of the concurrent Worker tier."""

    accepted_cids: List[str]
    support: Dict[str, int]
    predicted_hypothesis: str
    messages: List[Message] = field(default_factory=list)
    latency_ms: float = 0.0  # critical-path latency (max over concurrent workers)
    tokens: int = 0  # summed token consumption across workers


class WorkerTier:
    """A pool of concurrent Worker Agents."""

    def __init__(self, backend: LLMBackend, *, n_workers: int, temperature: float):
        self.backend = backend
        self.n_workers = n_workers
        self.temperature = temperature

    def _process_slice(self, worker_id: int, scenario: Scenario, claims) -> dict:
        """One worker: phrase a hypothesis over its slice of claims."""

        prompt = (
            f"Worker {worker_id} analytical pass over scenario {scenario.sid}.\n"
            f"Hypotheses: {scenario.hypotheses}\n"
            f"Claims: {[c.text for c in claims]}\n"
            "Generate candidate hypothesis support and a synthesis fragment."
        )
        resp = self.backend.generate(
            prompt, temperature=self.temperature, role="worker", max_tokens=384
        )
        support: Dict[str, int] = {}
        accepted: List[str] = []
        for c in claims:
            # No validation here: every claim is accepted at face value.
            accepted.append(c.cid)
            support[c.supports] = support.get(c.supports, 0) + 1
        # Each worker emits its own inter-agent message; the Governance Layer
        # mediates every one of them (Section 3.3.1).
        message = Message(
            recipient="validator",
            payload=f"worker{worker_id}_synthesis:{scenario.sid}:support={support}",
            classification="OFFICIAL",
            sensitivity=0.2,
        )
        return {
            "support": support,
            "accepted": accepted,
            "latency_ms": resp.latency_ms,
            "tokens": resp.total_tokens,
            "message": message,
        }

    def run(self, scenario: Scenario) -> WorkerOutput:
        # Partition claims across the worker pool for concurrent processing.
        slices = [scenario.claims[i :: self.n_workers] for i in range(self.n_workers)]
        slices = [s for s in slices if s]

        results = []
        with ThreadPoolExecutor(max_workers=self.n_workers) as pool:
            futures = [
                pool.submit(self._process_slice, wid, scenario, s)
                for wid, s in enumerate(slices)
            ]
            for f in futures:
                results.append(f.result())

        support: Dict[str, int] = {h: 0 for h in scenario.hypotheses}
        accepted: List[str] = []
        tokens = 0
        for r in results:
            for h, n in r["support"].items():
                support[h] = support.get(h, 0) + n
            accepted.extend(r["accepted"])
            tokens += r["tokens"]
        # Concurrency: critical-path latency is the slowest worker, not the sum.
        latency = max((r["latency_ms"] for r in results), default=0.0)

        # Deterministic argmax with a stable tie-break favouring the
        # lexicographically first hypothesis id (the benign default).
        predicted = min(scenario.hypotheses, key=lambda h: (-support.get(h, 0), h))

        # All concurrent workers' messages flow to the next tier.
        messages = [r["message"] for r in results]
        return WorkerOutput(
            accepted_cids=accepted,
            support=support,
            predicted_hypothesis=predicted,
            messages=messages,
            latency_ms=round(latency, 3),
            tokens=tokens,
        )
