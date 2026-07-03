"""
MemoryQueue — the fast, in-process buffer `track()` writes into.
`put()` never performs I/O and never blocks the caller for more than a
lock acquisition (microseconds), except when `overflow_policy="block"` is
configured — see the ticket's explicit "Overflow policy: Drop newest /
Drop oldest / Block. Configurable." requirement.
"""

from __future__ import annotations

import threading
from collections import deque

from costorah.reliability._types import OverflowPolicy, QueuedEvent


class MemoryQueue:
    def __init__(
        self,
        *,
        max_size: int = 10_000,
        overflow_policy: str = OverflowPolicy.DROP_OLDEST,
        block_timeout: float = 1.0,
    ) -> None:
        if max_size <= 0:
            raise ValueError("max_size must be positive")
        if overflow_policy not in OverflowPolicy.ALL:
            raise ValueError(f"overflow_policy must be one of {OverflowPolicy.ALL}")
        self._max_size = max_size
        self._overflow_policy = overflow_policy
        self._block_timeout = block_timeout
        self._items: deque[QueuedEvent] = deque()
        self._lock = threading.Lock()
        self._not_empty = threading.Condition(self._lock)
        self._not_full = threading.Condition(self._lock)
        self._dropped_count = 0

    def put(self, event: QueuedEvent) -> bool:
        """Returns True if the event was queued, False if it was dropped
        (only possible under drop_newest/drop_oldest at capacity)."""
        with self._lock:
            if len(self._items) < self._max_size:
                self._items.append(event)
                self._not_empty.notify()
                return True

            if self._overflow_policy == OverflowPolicy.DROP_NEWEST:
                self._dropped_count += 1
                return False

            if self._overflow_policy == OverflowPolicy.DROP_OLDEST:
                self._items.popleft()
                self._items.append(event)
                self._dropped_count += 1
                self._not_empty.notify()
                return True

            # BLOCK: wait for room, bounded by block_timeout so a caller
            # (and the whole application) can never hang indefinitely.
            deadline_ok = self._not_full.wait_for(
                lambda: len(self._items) < self._max_size, timeout=self._block_timeout
            )
            if not deadline_ok:
                self._dropped_count += 1
                return False
            self._items.append(event)
            self._not_empty.notify()
            return True

    def get_batch(self, max_items: int, *, timeout: float = 0.0) -> list[QueuedEvent]:
        """Drains up to `max_items`. With timeout=0 (default) this never
        blocks — used by the worker's poll loop. A positive timeout waits
        for at least one item, used by flush()/shutdown()."""
        with self._lock:
            if not self._items and timeout > 0:
                self._not_empty.wait(timeout=timeout)
            batch: list[QueuedEvent] = []
            while self._items and len(batch) < max_items:
                batch.append(self._items.popleft())
            if batch:
                self._not_full.notify_all()
            return batch

    def qsize(self) -> int:
        with self._lock:
            return len(self._items)

    @property
    def dropped_count(self) -> int:
        with self._lock:
            return self._dropped_count

    def is_empty(self) -> bool:
        with self._lock:
            return not self._items
