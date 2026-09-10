"""LLM backend abstraction.

GMAIS is model-agnostic by design: the thesis targets quantised open-weight
models (GGUF Q4_K_M, 3B-7B) running on consumer hardware, but the architecture
and its instrumentation must not depend on any particular inference engine. All
agents therefore talk to an :class:`LLMBackend`, and every call returns an
:class:`LLMResponse` carrying the token and latency telemetry that the Security
Tax measurement consumes.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass


def estimate_tokens(text: str) -> int:
    """Cheap, deterministic token estimate (~4 chars/token).

    Real backends return exact usage; this heuristic is used by the mock
    backend and as a fallback so that token accounting is always available.
    """

    if not text:
        return 0
    return max(1, len(text) // 4)


@dataclass
class LLMResponse:
    """Container for a single model completion plus its telemetry."""

    text: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float
    model: str
    role: str = "worker"
    # Which provider actually served this call (claude / openai / local / mock).
    # Set by multi-provider routing so the activity feed can show the real path.
    provider: str = ""

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class LLMBackend(abc.ABC):
    """Abstract inference backend."""

    name: str = "abstract"

    @abc.abstractmethod
    def generate(
        self,
        prompt: str,
        *,
        temperature: float,
        max_tokens: int = 512,
        role: str = "worker",
    ) -> LLMResponse:
        """Return a completion for ``prompt`` with full telemetry."""
        raise NotImplementedError
