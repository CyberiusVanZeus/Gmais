"""Anthropic (Claude) backend.

Uses a *light* Claude model by default (Haiku) to match the thesis's
resource-constrained brief while still allowing a hosted frontier model when the
operator wants one. The ``anthropic`` SDK is imported lazily so the rest of
GMAIS runs without it installed.

Configuration (environment variables):
* ``ANTHROPIC_API_KEY``  - required for real calls
* ``GMAIS_CLAUDE_MODEL`` - override the default model id
"""

from __future__ import annotations

import os
import time

from .base import LLMBackend, LLMResponse, estimate_tokens

# Light, low-cost Claude model id used by default (Haiku class).
DEFAULT_CLAUDE_MODEL = "claude-haiku-4-5-20251001"


class AnthropicBackend(LLMBackend):
    """Calls the Anthropic Messages API."""

    name = "claude"

    def __init__(self, *, model: str | None = None, api_key: str | None = None) -> None:
        # Lazy import keeps anthropic an optional dependency.
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "The 'anthropic' package is required for the Claude backend. "
                "Install it with `pip install anthropic`."
            ) from exc

        api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            # Surfaced to the caller so multi-provider routing can fall back.
            raise RuntimeError("ANTHROPIC_API_KEY is not set.")
        self.model = model or os.getenv("GMAIS_CLAUDE_MODEL", DEFAULT_CLAUDE_MODEL)
        self._client = anthropic.Anthropic(api_key=api_key)

    def generate(
        self,
        prompt: str,
        *,
        temperature: float,
        max_tokens: int = 512,
        role: str = "worker",
    ) -> LLMResponse:
        # Time the call so latency telemetry reflects real wall-clock cost.
        start = time.perf_counter()
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        latency_ms = (time.perf_counter() - start) * 1000.0

        # Concatenate text blocks from the response content.
        text = "".join(
            block.text for block in resp.content if getattr(block, "type", "") == "text"
        ).strip()

        # Prefer exact usage from the API; fall back to estimates if absent.
        usage = getattr(resp, "usage", None)
        prompt_tokens = getattr(usage, "input_tokens", None) or estimate_tokens(prompt)
        completion_tokens = getattr(usage, "output_tokens", None) or estimate_tokens(text)

        return LLMResponse(
            text=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=round(latency_ms, 3),
            model=self.model,
            role=role,
            provider="claude",
        )
