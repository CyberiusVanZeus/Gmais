"""OpenAI-compatible backend for hosted OpenAI *and* local models.

A single implementation serves two providers because both speak the OpenAI Chat
Completions API:

* ``openai`` - the hosted OpenAI API. Defaults to a *light* model (gpt-4o-mini)
  to honour the resource-constrained brief; override with ``GMAIS_OPENAI_MODEL``.
  Auth via ``OPENAI_API_KEY``.
* ``local``  - any local server exposing the same API: llama.cpp ``server``,
  LM Studio, or Ollama's OpenAI endpoint, typically hosting a quantised GGUF
  Q4_K_M model. Base URL via ``GMAIS_LOCAL_BASE_URL`` (default
  ``http://localhost:8080/v1``); model via ``GMAIS_LOCAL_MODEL``.

The ``openai`` SDK is imported lazily so it stays an optional dependency.
"""

from __future__ import annotations

import os
import random
import time

from .base import LLMBackend, LLMResponse, estimate_tokens
from .cost import METER

#: Transient-failure retry policy. A campaign issues thousands of sequential
#: calls, so the probability of meeting at least one rate-limit or transient
#: 5xx approaches certainty; without retries a single one discards the whole
#: run -- and, on a paid endpoint, the money already spent on it.
MAX_ATTEMPTS = 6
BACKOFF_BASE_S = 1.5
BACKOFF_CAP_S = 60.0

#: Substrings identifying errors that are worth retrying. Matching on the
#: message keeps this independent of the openai SDK's exception hierarchy,
#: which has changed across major versions.
_RETRYABLE = (
    "rate limit", "ratelimit", "429", "timeout", "timed out",
    "connection", "temporarily unavailable", "overloaded",
    "500", "502", "503", "504", "internal server error", "apierror",
)


def _is_retryable(exc: Exception) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    if "authentication" in text or "invalid_api_key" in text or "401" in text:
        return False  # a bad key will not fix itself; fail immediately
    if "insufficient_quota" in text or "billing" in text:
        return False  # out of credit: stop rather than hammer the endpoint
    return any(token in text for token in _RETRYABLE)

# Light hosted OpenAI default; cheap and fast, in keeping with the MVA brief.
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_LOCAL_MODEL = "local-model"
DEFAULT_LOCAL_BASE_URL = "http://localhost:8080/v1"


class OpenAICompatBackend(LLMBackend):
    """Backend that calls an OpenAI-compatible chat-completions endpoint."""

    def __init__(self, *, provider: str = "openai", model: str | None = None, api_key: str | None = None, base_url: str | None = None) -> None:
        # Lazy import keeps openai optional.
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "The 'openai' package is required for the OpenAI/local backend. "
                "Install it with `pip install openai`."
            ) from exc

        self.name = provider  # "openai" or "local"
        if provider == "local":
            # Local servers usually need no real key; base URL points at the host.
            base_url = base_url or os.getenv("GMAIS_LOCAL_BASE_URL", DEFAULT_LOCAL_BASE_URL)
            api_key = api_key or os.getenv("GMAIS_LOCAL_API_KEY", "not-needed")
            self.model = model or os.getenv("GMAIS_LOCAL_MODEL", DEFAULT_LOCAL_MODEL)
        else:
            # Hosted OpenAI: real key required; default base URL from the SDK.
            base_url = os.getenv("GMAIS_OPENAI_BASE_URL")  # None -> SDK default
            api_key = api_key or os.getenv("OPENAI_API_KEY")
            if not api_key:
                # Surfaced so multi-provider routing can fall back to local.
                raise RuntimeError("OPENAI_API_KEY is not set.")
            self.model = model or os.getenv("GMAIS_OPENAI_MODEL", DEFAULT_OPENAI_MODEL)

        # base_url=None lets the SDK use its built-in default for hosted OpenAI.
        self._client = OpenAI(base_url=base_url, api_key=api_key) if base_url else OpenAI(api_key=api_key)
        # Backoff jitter draws from its own generator so the campaign's global
        # seeding, and therefore its analytical determinism, is unaffected.
        self._jitter = random.Random(0xC0FFEE)

    def generate(
        self,
        prompt: str,
        *,
        temperature: float,
        max_tokens: int = 512,
        role: str = "worker",
    ) -> LLMResponse:
        # Time the round trip for real latency telemetry. Retries are timed
        # *inside* the measurement deliberately: a call that had to be retried
        # really did take that long to deliver a completion, and excluding the
        # wait would understate observed latency.
        start = time.perf_counter()
        resp = None
        last_exc: Exception | None = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                resp = self._client.chat.completions.create(
                    model=self.model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    messages=[{"role": "user", "content": prompt}],
                )
                break
            except Exception as exc:  # noqa: BLE001 - policy decided by _is_retryable
                last_exc = exc
                if attempt == MAX_ATTEMPTS - 1 or not _is_retryable(exc):
                    METER.record_failure()
                    raise
                METER.record_retry()
                # Exponential backoff with full jitter. A dedicated Random
                # instance is used so campaign-wide seeding is untouched.
                delay = min(BACKOFF_CAP_S, BACKOFF_BASE_S * (2 ** attempt))
                time.sleep(self._jitter.uniform(0.0, delay))
        if resp is None:  # pragma: no cover - defensive
            raise RuntimeError("completion failed") from last_exc
        latency_ms = (time.perf_counter() - start) * 1000.0

        text = (resp.choices[0].message.content or "").strip()
        usage = getattr(resp, "usage", None)
        if usage is not None:
            prompt_tokens = usage.prompt_tokens
            completion_tokens = usage.completion_tokens
        else:  # pragma: no cover - some servers omit usage
            prompt_tokens = estimate_tokens(prompt)
            completion_tokens = estimate_tokens(text)

        METER.record(prompt_tokens=prompt_tokens,
                     completion_tokens=completion_tokens, model=self.model)

        return LLMResponse(
            text=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=round(latency_ms, 3),
            model=self.model,
            role=role,
            provider=self.name,
        )
