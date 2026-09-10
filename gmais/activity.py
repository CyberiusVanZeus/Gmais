"""Operational activity recording for the live SSE feed.

Every stage of the architecture (ingest, worker spawn, hypothesis generation,
Admiralty grading, ACH, web-search corroboration, governance mediation, audit,
scoring) emits an activity event through a recorder. The web interface drains
the recorder's queue over Server-Sent Events so the operator watches the
behind-the-scenes work in real time, then receives the final result.

Two recorders are provided:
* :class:`ActivityRecorder` - thread-safe, queue-backed, for streaming.
* :func:`null_activity` - a no-op emit used by the CLI/tests where no live feed
  is needed.
"""

from __future__ import annotations

import queue
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ActivityEvent:
    """One operational step, with a lifecycle status."""

    seq: int
    stage: str  # e.g. "ingest", "worker", "validator", "governance", "score"
    message: str
    status: str = "running"  # "running" | "done" | "warn"
    data: Dict[str, Any] = field(default_factory=dict)
    t: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "seq": self.seq,
            "stage": self.stage,
            "message": self.message,
            "status": self.status,
            "data": self.data,
            "t": round(self.t, 3),
        }


# Sentinel placed on the queue to signal the stream is finished.
_SENTINEL = object()


class ActivityRecorder:
    """Thread-safe collector of activity events with a streaming queue."""

    def __init__(self) -> None:
        self._q: "queue.Queue[Any]" = queue.Queue()
        self.events: List[ActivityEvent] = []
        self._seq = 0
        self.result: Optional[Dict[str, Any]] = None

    def emit(self, stage: str, message: str, *, status: str = "running", **data: Any) -> None:
        """Record one activity step and push it onto the streaming queue."""
        self._seq += 1
        ev = ActivityEvent(seq=self._seq, stage=stage, message=message,
                            status=status, data=data)
        self.events.append(ev)
        self._q.put(ev)

    def push_result(self, result: Dict[str, Any]) -> None:
        """Enqueue an intermediate result (one per provider) without closing the stream."""
        self._q.put(("result", result))

    def finish(self, result: Dict[str, Any]) -> None:
        """Mark the run complete; enqueue a final result if non-empty, then close."""
        self.result = result
        if result:
            self._q.put(("result", result))
        self._q.put(_SENTINEL)

    def fail(self, message: str) -> None:
        """Abort the stream with an error event."""
        self.emit("error", message, status="warn")
        self._q.put(_SENTINEL)

    def stream(self):
        """Yield queued items (ActivityEvent or ('result', payload)) until done."""
        while True:
            item = self._q.get()
            if item is _SENTINEL:
                return
            yield item


def null_activity(*_args: Any, **_kwargs: Any) -> None:
    """A no-op emit callable for non-streaming contexts (CLI/tests)."""
    return None
