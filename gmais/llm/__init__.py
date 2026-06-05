"""LLM backend package."""

from __future__ import annotations

from .base import LLMBackend, LLMResponse, estimate_tokens
from .mock import DeterministicMockBackend


def build_backend(name: str = "mock", *, seed: int = 0, model: str = "gmais-mock") -> LLMBackend:
    """Factory: construct a backend by name.

    ``mock`` is fully offline and deterministic; ``openai`` targets any
    OpenAI-compatible server (llama.cpp, LM Studio, Ollama, OpenAI).
    """

    name = name.lower()
    if name == "mock":
        return DeterministicMockBackend(seed=seed, model=model)
    if name in ("openai", "openai_compat", "local"):
        from .openai_compat import OpenAICompatBackend

        return OpenAICompatBackend(model=model)
    raise ValueError(f"Unknown LLM backend: {name!r}")


__all__ = [
    "LLMBackend",
    "LLMResponse",
    "estimate_tokens",
    "DeterministicMockBackend",
    "build_backend",
]
