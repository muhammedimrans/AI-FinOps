"""
Shared types for the reliability layer (EP-18.3). One event flows:
MemoryQueue -> BackgroundWorker -> PersistentQueue -> Compression ->
RetryScheduler -> CircuitBreaker -> ConnectionPool -> Usage API.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


@dataclass(slots=True)
class QueuedEvent:
    """One usage payload in flight through the reliability pipeline.
    `payload` is the already-validated, wire-format (snake_case) dict
    `Costorah.track()` builds — the same shape `_http.py` posts today."""

    payload: dict[str, Any]
    event_id: str = field(default_factory=lambda: uuid4().hex)
    attempts: int = 0


class OverflowPolicy:
    """Memory queue overflow policy — configurable per the ticket."""

    DROP_NEWEST = "drop_newest"
    DROP_OLDEST = "drop_oldest"
    BLOCK = "block"

    ALL = (DROP_NEWEST, DROP_OLDEST, BLOCK)
