"""
EventQueue — bounded in-memory queue collectors push into.

Design: `Memory Queue -> Retry Queue -> HTTP Sender` (per EP-17). This
module is the first stage. When the in-memory queue is full (the producer
side — collection — is outpacing the consumer side — delivery, e.g. during
a COSTORAH outage), new events overflow directly to the durable SQLite
store instead of blocking the collection loop or being dropped. That
overflow path is exactly how "never lose telemetry" holds even under
sustained backpressure, not just brief network blips.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from costorah_agent.queue.sqlite_store import SQLiteEventStore


@dataclass(slots=True)
class QueueItem:
    event_id: str
    payload: dict[str, Any]


class EventQueue:
    """Bounded in-memory FIFO with disk overflow on backpressure."""

    def __init__(self, max_size: int, overflow_store: SQLiteEventStore) -> None:
        self._queue: asyncio.Queue[QueueItem] = asyncio.Queue(maxsize=max_size)
        self._overflow_store = overflow_store
        self._overflowed_total = 0

    async def put(self, event_id: str, payload: dict[str, Any]) -> None:
        """Enqueue an event. Never blocks and never raises — overflows to
        disk rather than applying backpressure to the collection loop."""
        item = QueueItem(event_id=event_id, payload=payload)
        try:
            self._queue.put_nowait(item)
        except asyncio.QueueFull:
            self._overflowed_total += 1
            await self._overflow_store.enqueue(event_id, payload)

    def get_batch_nowait(self, max_items: int) -> list[QueueItem]:
        """Drain up to `max_items` without blocking. Returns [] if empty."""
        items: list[QueueItem] = []
        for _ in range(max_items):
            try:
                items.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return items

    def qsize(self) -> int:
        return self._queue.qsize()

    @property
    def overflowed_total(self) -> int:
        return self._overflowed_total
