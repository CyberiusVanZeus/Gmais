"""LLM backend package.

Exposes a factory for single-provider backends and a helper for the
multi-provider round-robin router used by the web interface.

Provider names:
* ``claude`` - Anthropic Claude (light Haiku model by default)
* ``openai`` - hosted OpenAI (light gpt-4o-mini by default)
* ``local``  - any local OpenAI-compatible server (llama.cpp / LM Studio / Ollama)
* ``mock``   - deterministic offline stub, for tests/CI only
"""

from __future__ import annotations

from typing import List, Optional

from .base import LLMBackend, LLMResponse, estimate_tokens
from .mock import DeterministicMockBackend
from .multi import MultiProviderBackend

#: Providers a user may legitimately select from the web interface.
USER_PROVIDERS = ("claude", "openai", "local")


def build_backend(
    name: str = "mock",
    *,
    seed: int = 0,
    model: str = "gmais-mock",
    api_keys: Optional[dict] = None,
) -> LLMBackend:
    """Factory: construct a single backend by provider name.

    ``api_keys`` is an optional dict mapping provider name to key string,
    e.g. ``{"openai": "sk-...", "claude": "sk-ant-..."}``.  Values override
    the corresponding environment variables so the web UI can supply them at
    request time without mutating the process environment.
    """
    keys = api_keys or {}
    name = name.lower()
    if name == "mock":
        return DeterministicMockBackend(seed=seed, model=model)
    if name == "claude":
        from .anthropic_backend import AnthropicBackend

        return AnthropicBackend(api_key=keys.get("claude") or None)
    if name in ("openai", "local", "openai_compat"):
        from .openai_compat import OpenAICompatBackend

        provider = "local" if name == "local" else "openai"
        return OpenAICompatBackend(provider=provider, api_key=keys.get(provider) or None)
    raise ValueError(f"Unknown LLM backend: {name!r}")


def build_multi_backend(
    providers: List[str],
    *,
    seed: int = 0,
    activity=None,
    api_keys: Optional[dict] = None,
) -> MultiProviderBackend:
    """Construct a round-robin multi-provider backend with local fallback."""

    return MultiProviderBackend(providers, seed=seed, activity=activity, api_keys=api_keys)


__all__ = [
    "LLMBackend",
    "LLMResponse",
    "estimate_tokens",
    "DeterministicMockBackend",
    "MultiProviderBackend",
    "build_backend",
    "build_multi_backend",
    "USER_PROVIDERS",
]
