"""Local model backend with built-in web search augmentation.

Targets any OpenAI-compatible local server (Ollama, llama.cpp, LM Studio).
Default: Ollama at http://localhost:11434/v1 running llama3.2:1b.

Web search augmentation:
  Before each LLM call the backend extracts the first meaningful noun-phrase
  from the prompt, queries DuckDuckGo's free zero-click JSON API (no key
  required), and prepends up to three result snippets as context.  If the
  search times out or fails the prompt is sent unmodified.

Environment overrides:
  GMAIS_LOCAL_BASE_URL  — base URL  (default http://localhost:11434/v1)
  GMAIS_LOCAL_MODEL     — model tag  (default llama3.2:1b)
  GMAIS_LOCAL_API_KEY   — API key    (default "not-needed")
  GMAIS_LOCAL_WEBSEARCH — set to "0" to disable search augmentation
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request
from typing import List

from .base import LLMBackend, LLMResponse, estimate_tokens

DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_MODEL = "llama3.2:1b"
_SEARCH_TIMEOUT = 5.0   # seconds; non-blocking on failure
_MAX_SNIPPETS = 3
_SNIPPET_CHARS = 220    # characters per snippet kept in prompt


def _ddg_search(query: str) -> List[str]:
    """Return up to _MAX_SNIPPETS plain-text snippets from DuckDuckGo zero-click API."""
    try:
        url = (
            "https://api.duckduckgo.com/?"
            + urllib.parse.urlencode({"q": query, "format": "json",
                                      "no_html": "1", "skip_disambig": "1"})
        )
        req = urllib.request.Request(url, headers={"User-Agent": "GMAIS/1.0"})
        with urllib.request.urlopen(req, timeout=_SEARCH_TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8", errors="ignore"))

        snippets: List[str] = []
        # Primary abstract (Wikipedia-style).
        abstract = (data.get("AbstractText") or "").strip()
        if abstract:
            snippets.append(abstract[:_SNIPPET_CHARS])
        # Related topics.
        for topic in data.get("RelatedTopics", []):
            text = (topic.get("Text") or "").strip()
            if text and len(snippets) < _MAX_SNIPPETS:
                snippets.append(text[:_SNIPPET_CHARS])
        return snippets
    except Exception:
        return []


def _extract_query(prompt: str) -> str:
    """Pull the first capitalised noun-phrase or first N words as a search query."""
    # Try to find a quoted entity or capitalised phrase first.
    m = re.search(r'"([^"]{4,60})"', prompt)
    if m:
        return m.group(1)
    # First sentence, stripped to ≤10 words.
    first_sentence = re.split(r"[.!?\n]", prompt.strip())[0]
    words = first_sentence.split()
    return " ".join(words[:10])


def _augment_prompt(prompt: str) -> str:
    """Prepend DuckDuckGo search results to the prompt as grounding context."""
    query = _extract_query(prompt)
    if not query:
        return prompt
    snippets = _ddg_search(query)
    if not snippets:
        return prompt
    context = "\n".join(f"- {s}" for s in snippets)
    return (
        f"[Web search context for '{query}']\n{context}\n\n"
        f"[Task]\n{prompt}"
    )


class LocalBackend(LLMBackend):
    """OpenAI-compatible local backend (Ollama / llama.cpp) with web search."""

    name = "local"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
    ) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "The 'openai' package is required for the local backend."
            ) from exc

        self._base_url = base_url or os.getenv("GMAIS_LOCAL_BASE_URL", DEFAULT_BASE_URL)
        self.model = model or os.getenv("GMAIS_LOCAL_MODEL", DEFAULT_MODEL)
        _key = api_key or os.getenv("GMAIS_LOCAL_API_KEY", "not-needed")
        self._client = OpenAI(base_url=self._base_url, api_key=_key)
        self._websearch = os.getenv("GMAIS_LOCAL_WEBSEARCH", "1") != "0"

    def generate(
        self,
        prompt: str,
        *,
        temperature: float,
        max_tokens: int = 512,
        role: str = "worker",
    ) -> LLMResponse:
        if self._websearch:
            prompt = _augment_prompt(prompt)

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
        prompt_tokens = getattr(usage, "prompt_tokens", None) or estimate_tokens(prompt)
        completion_tokens = getattr(usage, "completion_tokens", None) or estimate_tokens(text)

        return LLMResponse(
            text=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=round(latency_ms, 3),
            model=self.model,
            role=role,
            provider="local",
        )
