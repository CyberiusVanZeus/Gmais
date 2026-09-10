"""Wall-clock instrumentation for the Security-Tax measurement (Section 3.3.4).

The Security Tax is a claim about *cost*, so the latency terms that enter it
have to be defensible. GMAIS distinguishes two latency sources and never mixes
them:

**Measured framework latency.** Everything the Governance Layer and the
tradecraft components actually execute -- HMAC delegation-token verification,
the fG(e) policy evaluation, SHA-256 audit-chain construction, named-entity
redaction, mediation-queue bookkeeping, Admiralty grading and ACH matrix
evaluation -- is real Python doing real work. This module times it with
:func:`time.perf_counter_ns`, the highest-resolution monotonic clock the
platform exposes, and reports it as an empirical distribution over thousands of
events. These are measurements.

**Modelled inference latency.** Time spent inside the language model is a
property of the serving stack, not of GMAIS. Under the deterministic backend it
is produced by an explicit cost model (:mod:`gmais.llm.mock`); under a live
backend it is the observed wall clock of the completion call. It is carried in
a separate field throughout, and any figure or table that includes it is
labelled accordingly.

Keeping the two separate is what lets the governance overhead -- the quantity
H2 is actually about -- be reported as a measurement even when the campaign is
reproduced offline without a GPU.

Resolution note
---------------
Individual governance operations run in the microsecond range, near enough to
the clock's resolution that a single sample is untrustworthy. The campaign
therefore aggregates thousands of per-event samples and reports medians with
bootstrap intervals rather than single-shot timings, and
:meth:`ComponentTimings.clock_resolution_ns` records the measured granularity
of the clock so the reader can judge the floor.
"""

from __future__ import annotations

import platform
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Dict, Iterator, List

#: Components timed independently within a single observation.
COMPONENTS = (
    "worker_tier",       # concurrent Worker pass (critical path)
    "validator",         # Admiralty grading + ACH critique loop
    "governance_total",  # every mediated event, end to end
    "policy_eval",       # fG(e): token verify + need-to-know + sensitivity
    "audit_record",      # SHA-256 hash-chain append
    "redaction",         # named-entity need-to-know masking
    "queue",             # mediation-queue enqueue/dequeue bookkeeping
)


def clock_resolution_ns(samples: int = 2000) -> float:
    """Empirically measure the smallest non-zero tick of the process clock."""

    deltas: List[int] = []
    for _ in range(samples):
        a = time.perf_counter_ns()
        b = time.perf_counter_ns()
        while b == a:
            b = time.perf_counter_ns()
        deltas.append(b - a)
    return float(min(deltas))


@dataclass
class ComponentTimings:
    """Accumulated wall-clock nanoseconds for one observation."""

    totals_ns: Dict[str, int] = field(default_factory=dict)
    counts: Dict[str, int] = field(default_factory=dict)

    def add(self, component: str, elapsed_ns: int) -> None:
        """Record one timed occurrence of ``component``."""

        self.totals_ns[component] = self.totals_ns.get(component, 0) + elapsed_ns
        self.counts[component] = self.counts.get(component, 0) + 1

    def reattribute(self, frm: str, to: str, elapsed_ns: int) -> None:
        """Move ``elapsed_ns`` from one component's total to another's.

        Used where a nested operation is timed by the callee rather than the
        caller: the caller's enclosing measurement already contains the nested
        cost, so charging the nested component without discharging the enclosing
        one would double-count it. Occurrence counts are adjusted for the
        receiving component only -- the enclosing block still happened once.
        """

        if elapsed_ns <= 0:
            return
        self.totals_ns[frm] = self.totals_ns.get(frm, 0) - elapsed_ns
        self.add(to, elapsed_ns)

    def ms(self, component: str) -> float:
        """Total measured milliseconds for ``component``."""

        return self.totals_ns.get(component, 0) / 1e6

    def n(self, component: str) -> int:
        return self.counts.get(component, 0)

    def per_event_us(self, component: str) -> float:
        """Mean measured microseconds per event for ``component``."""

        count = self.counts.get(component, 0)
        if not count:
            return 0.0
        return self.totals_ns[component] / count / 1e3

    @contextmanager
    def measure(self, component: str) -> Iterator[None]:
        """Time a block and attribute it to ``component``."""

        start = time.perf_counter_ns()
        try:
            yield
        finally:
            self.add(component, time.perf_counter_ns() - start)

    def as_dict(self) -> Dict[str, float]:
        """Flat, CSV-friendly view: ``measured_<component>_ms``."""

        out: Dict[str, float] = {}
        for component in COMPONENTS:
            out[f"measured_{component}_ms"] = round(self.ms(component), 6)
        return out


class NullTimings(ComponentTimings):
    """No-op timer used when ``measure_wallclock`` is disabled."""

    @contextmanager
    def measure(self, component: str) -> Iterator[None]:
        yield

    def add(self, component: str, elapsed_ns: int) -> None:  # pragma: no cover
        return


def environment_manifest() -> Dict[str, object]:
    """Platform facts a reviewer needs to interpret the measured timings."""

    import os

    return {
        "python_version": sys.version.split()[0],
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "processor": platform.processor() or platform.machine(),
        "cpu_count": os.cpu_count(),
        "clock": "time.perf_counter_ns",
        "clock_resolution_ns": clock_resolution_ns(),
    }
