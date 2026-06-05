"""Deterministic mock backend.

The thesis runs GMAIS on quantised local models, but reproducing the factorial
ablation must not require a GPU or network access. This backend produces
*deterministic* completions and *plausible* token/latency telemetry as a pure
function of the prompt, role and global seed. Because the analytical logic of
the agents (Admiralty grading, ACH ranking, injection detection) lives in
Python rather than in the model, swapping this mock for a real backend changes
the prose quality of outputs but not the structure of the experiment.

Latency is modelled, not measured, so that results are bit-for-bit reproducible
under deterministic seeding (Algorithm 1, step 3). A real backend reports wall
clock latency instead; the Security-Tax machinery is agnostic to the source.
"""

from __future__ import annotations

import hashlib

from .base import LLMBackend, LLMResponse, estimate_tokens

# Per-role fixed latency floor (ms) and per-token marginal cost (ms/token).
# The Validator runs colder and more deliberately than the Workers, which the
# thesis operationalises as T=0.2 vs T=0.7 (Section 3.3.2).
_ROLE_BASE_MS = {"worker": 45.0, "validator": 70.0, "synthesis": 55.0}
_ROLE_PER_TOKEN_MS = {"worker": 1.8, "validator": 2.6, "synthesis": 2.0}


class DeterministicMockBackend(LLMBackend):
    """Seeded, offline stand-in for a quantised local model."""

    name = "mock"

    def __init__(self, *, seed: int = 0, model: str = "gmais-mock") -> None:
        self.seed = seed
        self.model = model

    def _digest(self, prompt: str, temperature: float, role: str) -> int:
        key = f"{self.seed}|{role}|{temperature:.3f}|{prompt}".encode("utf-8")
        return int.from_bytes(hashlib.sha256(key).digest()[:8], "big")

    def generate(
        self,
        prompt: str,
        *,
        temperature: float,
        max_tokens: int = 512,
        role: str = "worker",
    ) -> LLMResponse:
        h = self._digest(prompt, temperature, role)

        prompt_tokens = estimate_tokens(prompt)
        # Completion length: a seeded fraction of the budget, biased upward by
        # temperature (hotter sampling produces longer exploratory text).
        frac = 0.35 + 0.50 * ((h % 1000) / 1000.0)
        frac = min(1.0, frac * (0.85 + 0.30 * temperature))
        completion_tokens = max(8, int(max_tokens * frac))

        base = _ROLE_BASE_MS.get(role, 45.0)
        per_token = _ROLE_PER_TOKEN_MS.get(role, 1.8)
        # Deterministic +/-12% jitter so within-tier z-scores have variance.
        jitter = 1.0 + (((h >> 8) % 240) - 120) / 1000.0
        latency_ms = (base + per_token * completion_tokens) * jitter

        text = (
            f"[{role}|T={temperature:.1f}] deterministic completion "
            f"#{h % 100000:05d} ({completion_tokens} tok)"
        )

        return LLMResponse(
            text=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=round(latency_ms, 3),
            model=self.model,
            role=role,
        )
