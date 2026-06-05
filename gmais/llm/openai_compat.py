"""OpenAI-compatible backend for real local/remote inference.

Works against any server that speaks the OpenAI Chat Completions API, which
covers the deployment targets the thesis cares about:

* ``llama.cpp`` server (``./server --api ...``) hosting a GGUF Q4_K_M model
* LM Studio's local server
* Ollama's OpenAI-compatible endpoint
* the hosted OpenAI API (for convenience / comparison)

Point it at a base URL with ``GMAIS_LLM_BASE_URL`` (default
``http://localhost:8080/v1``) and, where required, ``GMAIS_LLM_API_KEY``.
The ``openai`` package is imported lazily so the rest of GMAIS runs without it.
"""

from __future__ import annotations

import os
import time

from .base import LLMBackend, LLMResponse, estimate_tokens


class OpenAICompatBackend(LLMBackend):
    """Backend that calls an OpenAI-compatible chat-completions endpoint."""

    name = "openai"

    def __init__(self, *, model: str = "local-model") -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "The 'openai' package is required for the OpenAI-compatible "
                "backend. Install it with `pip install openai`."
            ) from exc

        base_url = os.getenv("GMAIS_LLM_BASE_URL", "http://localhost:8080/v1")
        api_key = os.getenv("GMAIS_LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or "not-needed"
        self.model = os.getenv("GMAIS_LLM_MODEL", model)
        self._client = OpenAI(base_url=base_url, api_key=api_key)

    def generate(
        self,
        prompt: str,
        *,
        temperature: float,
        max_tokens: int = 512,
        role: str = "worker",
    ) -> LLMResponse:
        start = time.perf_counter()
        resp = self._client.chat.completions.create(
            model=self.model,
            temperature=temperature,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        latency_ms = (time.perf_counter() - start) * 1000.0

        text = (resp.choices[0].message.content or "").strip()
        usage = getattr(resp, "usage", None)
        if usage is not None:
            prompt_tokens = usage.prompt_tokens
            completion_tokens = usage.completion_tokens
        else:  # pragma: no cover - some servers omit usage
            prompt_tokens = estimate_tokens(prompt)
            completion_tokens = estimate_tokens(text)

        return LLMResponse(
            text=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=round(latency_ms, 3),
            model=self.model,
            role=role,
        )
