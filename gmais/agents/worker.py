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
from typing import Dict, List, Optional

from ..llm.base import LLMBackend
from ..noise import NoiseModel
from ..scenarios import Scenario
from ..timing import ComponentTimings, NullTimings

#: How heavily an anchored Worker over-weights an unattributed allegation that
#: names the actor, relative to a claim it received through normal channels.
#: A Worker performs no source validation, so the only thing distinguishing the
#: allegation is its vividness -- the named actor. Section 3.3.1.
ANCHOR_WEIGHT = 2


@dataclass
class Message:
    """A lightweight inter-agent message the orchestrator wraps as an Event."""

    recipient: str
    payload: str
    classification: str = "UNCLASSIFIED"
    sensitivity: float = 0.1
    # Worker-to-worker peer exchange: the Governance Layer applies named-entity
    # redaction (need-to-know) to these before transmission, to reduce bias.
    peer: bool = False
    entities: List[str] = field(default_factory=list)


@dataclass
class WorkerOutput:
    """Aggregated product of the concurrent Worker tier."""

    accepted_cids: List[str]
    support: Dict[str, int]
    predicted_hypothesis: str
    messages: List[Message] = field(default_factory=list)
    peer_messages: List[Message] = field(default_factory=list)
    latency_ms: float = 0.0  # critical-path latency (max over concurrent workers)
    tokens: int = 0  # summed token consumption across workers
    #: Workers that herded onto the entity-anchored hypothesis during peer
    #: exchange. Structurally zero when peer traffic is entity-redacted.
    anchored_workers: int = 0
    #: Support votes added by anchoring (0 under governance).
    anchor_votes: int = 0


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
        # Worker-to-worker peer share: carries entity-bearing claim text so that
        # need-to-know entity redaction has substance to act on (bias control).
        evidence_snippet = " ".join(c.text for c in claims)
        peer = Message(
            recipient="worker_peers",
            payload=f"peer_synthesis from worker{worker_id} ({scenario.sid}): {evidence_snippet}",
            classification="OFFICIAL",
            sensitivity=0.2,
            peer=True,
            entities=list(scenario.entities),
        )
        return {
            "support": support,
            "accepted": accepted,
            "latency_ms": resp.latency_ms,
            "tokens": resp.total_tokens,
            "message": message,
            "peer": peer,
            "provider": resp.provider,  # which model served this worker
        }

    @staticmethod
    def _anchor_target(scenario: Scenario, claims) -> Optional[str]:
        """The hypothesis an unvalidating Worker herds onto, or ``None``.

        The anchor is an *unattributed allegation that names the actor*: the
        corpus phrases injected claims as "Unverified channels allege ... proves
        <actor> ..." with no reporting entity attached, whereas genuine claims
        are attributed ("<reporter> reporting indicates ..."). A Worker does no
        source validation, so what makes the allegation salient is simply the
        named actor.

        This is exactly the cue need-to-know redaction destroys: once the actor
        is masked to ``[ENTITY_n]`` the allegation loses its referent and the
        Worker is left weighing claims on their analytical substance. The caller
        therefore skips this method entirely when peer traffic is redacted.
        """

        if not scenario.entities:
            return None
        actor = scenario.entities[0]
        reporter = scenario.entities[1] if len(scenario.entities) > 1 else None

        votes: Dict[str, int] = {}
        for claim in claims:
            names_actor = actor in claim.text
            attributed = bool(reporter) and reporter in claim.text
            if names_actor and not attributed:
                votes[claim.supports] = votes.get(claim.supports, 0) + 1
        if not votes:
            return None
        return max(votes, key=lambda h: (votes[h], h))

    def run(self, scenario: Scenario, *, peer_redaction: bool = False,
            noise: NoiseModel | None = None,
            timings: ComponentTimings | None = None,
            activity=None) -> WorkerOutput:
        # ``activity`` is an optional emit callable for the live operational feed.
        # ``peer_redaction`` reports whether the Governance Layer will mask named
        # entities on worker-to-worker traffic; when it will, the anchoring cue
        # is unavailable and the herding pathway is closed.
        emit = activity or (lambda *a, **k: None)
        noise = noise or NoiseModel.disabled()
        timings = timings or NullTimings()

        # Partition claims across the worker pool for concurrent processing.
        slices = [scenario.claims[i :: self.n_workers] for i in range(self.n_workers)]
        slices = [s for s in slices if s]
        emit("worker", f"Spawning {len(slices)} concurrent Worker Agents (T={self.temperature})")

        results = []
        with timings.measure("worker_tier"):
            with ThreadPoolExecutor(max_workers=self.n_workers) as pool:
                futures = [
                    pool.submit(self._process_slice, wid, scenario, s)
                    for wid, s in enumerate(slices)
                ]
                for f in futures:
                    results.append(f.result())

        # Surface which providers actually served the worker calls.
        providers = sorted({r.get("provider", "") for r in results if r.get("provider")})
        emit("worker", "Workers generated candidate hypotheses concurrently",
             status="done", providers=providers)

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

        # --- Peer-exchange round (worker-to-worker, Section 3.3.1) --------- #
        # Each Worker now sees its peers' synthesis. Where that traffic still
        # carries named entities, a Worker may herd onto the entity-anchored
        # hypothesis instead of weighing the evidence; where the Governance
        # Layer has masked the entities, the cue is gone and no herding occurs.
        anchored_workers = 0
        anchor_votes = 0
        if not peer_redaction:
            for wid, own_slice in enumerate(slices):
                if not noise.worker_anchors(scenario.sid, wid):
                    continue
                # A Worker anchors on what its *peers* sent it, not its own slice.
                peer_claims = [
                    c for j, s in enumerate(slices) if j != wid for c in s
                ]
                target = self._anchor_target(scenario, peer_claims)
                if target is None:
                    continue
                anchored_workers += 1
                anchor_votes += ANCHOR_WEIGHT
                support[target] = support.get(target, 0) + ANCHOR_WEIGHT
            if anchored_workers:
                emit("worker", f"{anchored_workers} Worker(s) herded onto the "
                     "entity-anchored hypothesis during unmediated peer exchange")
        else:
            emit("worker", "Peer exchange will be entity-redacted by the "
                 "Governance Layer - anchoring cue unavailable")

        # Deterministic argmax with a stable tie-break favouring the
        # lexicographically first hypothesis id (the benign default).
        predicted = min(scenario.hypotheses, key=lambda h: (-support.get(h, 0), h))

        # All concurrent workers' messages flow to the next tier; their peer
        # broadcasts circulate within the tier under governance mediation.
        messages = [r["message"] for r in results]
        peer_messages = [r["peer"] for r in results]
        return WorkerOutput(
            accepted_cids=accepted,
            support=support,
            predicted_hypothesis=predicted,
            messages=messages,
            peer_messages=peer_messages,
            latency_ms=round(latency, 3),
            tokens=tokens,
            anchored_workers=anchored_workers,
            anchor_votes=anchor_votes,
        )
