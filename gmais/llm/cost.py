"""Token and cost accounting for paid inference backends.

A campaign against a hosted API is a spend, and a spend that cannot be
attributed is a spend that cannot be justified in a methods section. This module
meters every completion -- calls, prompt tokens, completion tokens and the
resulting cost -- so the run reports what it consumed rather than leaving the
reader (or the person paying) to infer it from an invoice.

Prices are US dollars per million tokens and are recorded in the results
manifest alongside the figures they produced, because they change: a cost
reported without the price table that generated it is not reproducible.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Dict, Optional

#: USD per 1M tokens, (prompt, completion). Verified against OpenAI's published
#: pricing at the time of the campaign; recorded in MANIFEST.json with the run.
PRICING_USD_PER_MTOK: Dict[str, tuple] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
}


def price_for(model: str) -> Optional[tuple]:
    """Return (prompt, completion) USD/Mtok for ``model``, or None if unpriced."""

    if model in PRICING_USD_PER_MTOK:
        return PRICING_USD_PER_MTOK[model]
    # Hosted model ids often carry a dated suffix (gpt-4o-mini-2024-07-18).
    for known, price in PRICING_USD_PER_MTOK.items():
        if model.startswith(known):
            return price
    return None


@dataclass
class CostMeter:
    """Thread-safe accumulator for API consumption.

    The Worker tier calls the backend from a ThreadPoolExecutor, so the counters
    are mutated concurrently and every update is taken under a lock.
    """

    model: str = ""
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    retries: int = 0
    failures: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record(self, *, prompt_tokens: int, completion_tokens: int,
               model: str = "") -> None:
        with self._lock:
            self.calls += 1
            self.prompt_tokens += prompt_tokens
            self.completion_tokens += completion_tokens
            if model and not self.model:
                self.model = model

    def record_retry(self) -> None:
        with self._lock:
            self.retries += 1

    def record_failure(self) -> None:
        with self._lock:
            self.failures += 1

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def cost_usd(self) -> Optional[float]:
        price = price_for(self.model)
        if price is None:
            return None
        prompt_price, completion_price = price
        return (self.prompt_tokens / 1e6 * prompt_price
                + self.completion_tokens / 1e6 * completion_price)

    def as_dict(self) -> Dict[str, object]:
        cost = self.cost_usd
        return {
            "model": self.model,
            "calls": self.calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "retries": self.retries,
            "failures": self.failures,
            "pricing_usd_per_mtok": price_for(self.model),
            "cost_usd": round(cost, 6) if cost is not None else None,
        }

    def summary(self) -> str:
        cost = self.cost_usd
        money = f"${cost:.4f}" if cost is not None else "unpriced"
        return (f"{self.calls:,} calls · {self.prompt_tokens:,} prompt + "
                f"{self.completion_tokens:,} completion tokens · {money}"
                + (f" · {self.retries} retries" if self.retries else "")
                + (f" · {self.failures} FAILURES" if self.failures else ""))


#: Process-wide meter, so a campaign can report its spend without threading a
#: meter through every agent constructor.
METER = CostMeter()


def reset_meter(model: str = "") -> CostMeter:
    """Start a fresh accounting period."""

    global METER
    METER = CostMeter(model=model)
    return METER
