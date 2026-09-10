"""Multi-provider routing: round-robin, no cross-provider fallback.

Each selected provider runs independently. If it fails at construction time it
is skipped with a warning; if it fails at call time the error surfaces
immediately — there is no silent fallback to another provider. This lets the
operator see exactly which model is responsible for each result.

``mock`` is never offered as a user option; it is only used internally by
tests/CI via ``GMAIS_ALLOW_MOCK``.
"""

from __future__ import annotations

import itertools
import os
from typing import Callable, List, Optional

from .base import LLMBackend, LLMResponse

ActivityFn = Callable[..., None]


class MultiProviderBackend(LLMBackend):
    """Round-robins across selected providers with no cross-provider fallback."""

    name = "multi"

    def __init__(
        self,
        providers: List[str],
        *,
        seed: int = 0,
        activity: Optional[ActivityFn] = None,
        api_keys: Optional[dict] = None,
    ) -> None:
        if not providers:
            providers = ["local"]
        self.requested = list(providers)
        self.seed = seed
        self._activity = activity
        self._api_keys: dict = api_keys or {}

        self._backends: dict[str, LLMBackend] = {}
        self._available: List[str] = []
        for p in self.requested:
            backend = self._try_build(p)
            if backend is not None:
                self._backends[p] = backend
                self._available.append(p)

        # Mock only as last resort for offline tests/CI, never for real runs.
        if not self._available and os.getenv("GMAIS_ALLOW_MOCK"):
            mock = self._try_build("mock")
            if mock:
                self._backends["mock"] = mock
                self._available = ["mock"]

        if not self._available:
            raise RuntimeError(
                "No LLM provider could be initialised. Configure at least one of "
                "ANTHROPIC_API_KEY / OPENAI_API_KEY / a local OpenAI-compatible "
                "server (GMAIS_LOCAL_BASE_URL)."
            )

        self._cycle = itertools.cycle(self._available)

    def _try_build(self, provider: str) -> Optional[LLMBackend]:
        try:
            if provider == "claude":
                from .anthropic_backend import AnthropicBackend
                return AnthropicBackend(api_key=self._api_keys.get("claude") or None)
            if provider == "openai":
                from .openai_compat import OpenAICompatBackend
                return OpenAICompatBackend(provider="openai",
                                           api_key=self._api_keys.get("openai") or None)
            if provider == "local":
                from .local_backend import LocalBackend
                return LocalBackend(
                    base_url=self._api_keys.get("local_url") or None,
                    api_key=self._api_keys.get("local") or None,
                )
            if provider == "mock":
                from .mock import DeterministicMockBackend
                return DeterministicMockBackend(seed=self.seed)
        except Exception as exc:
            if self._activity:
                self._activity("provider", f"{provider} unavailable ({exc}); skipping",
                               status="warn")
        return None

    @property
    def available_providers(self) -> List[str]:
        return list(self._available)

    def generate(
        self,
        prompt: str,
        *,
        temperature: float,
        max_tokens: int = 512,
        role: str = "worker",
    ) -> LLMResponse:
        provider = next(self._cycle)
        backend = self._backends[provider]
        # No fallback — let the error propagate so the caller sees which model failed.
        resp = backend.generate(prompt, temperature=temperature, max_tokens=max_tokens, role=role)
        if not resp.provider:
            resp.provider = provider
        return resp
