from __future__ import annotations

import threading
import time

import pytest

from costorah.reliability import MemoryQueue, OverflowPolicy, QueuedEvent


def _event(n: int) -> QueuedEvent:
    return QueuedEvent(payload={"n": n})


def test_put_and_get_batch_fifo_order() -> None:
    q = MemoryQueue(max_size=10)
    for i in range(5):
        assert q.put(_event(i)) is True
    batch = q.get_batch(10)
    assert [e.payload["n"] for e in batch] == [0, 1, 2, 3, 4]
    assert q.is_empty()


def test_get_batch_respects_max_items() -> None:
    q = MemoryQueue(max_size=10)
    for i in range(5):
        q.put(_event(i))
    batch = q.get_batch(3)
    assert len(batch) == 3
    assert q.qsize() == 2


def test_drop_newest_overflow_policy() -> None:
    q = MemoryQueue(max_size=2, overflow_policy=OverflowPolicy.DROP_NEWEST)
    assert q.put(_event(1)) is True
    assert q.put(_event(2)) is True
    assert q.put(_event(3)) is False  # dropped
    assert q.dropped_count == 1
    batch = q.get_batch(10)
    assert [e.payload["n"] for e in batch] == [1, 2]


def test_drop_oldest_overflow_policy() -> None:
    q = MemoryQueue(max_size=2, overflow_policy=OverflowPolicy.DROP_OLDEST)
    assert q.put(_event(1)) is True
    assert q.put(_event(2)) is True
    assert q.put(_event(3)) is True  # evicts 1
    assert q.dropped_count == 1
    batch = q.get_batch(10)
    assert [e.payload["n"] for e in batch] == [2, 3]


def test_block_overflow_policy_waits_for_room() -> None:
    q = MemoryQueue(max_size=1, overflow_policy=OverflowPolicy.BLOCK, block_timeout=2.0)
    assert q.put(_event(1)) is True

    def drain_after_delay() -> None:
        time.sleep(0.1)
        q.get_batch(1)

    threading.Thread(target=drain_after_delay).start()
    start = time.monotonic()
    assert q.put(_event(2)) is True
    assert time.monotonic() - start < 2.0


def test_block_overflow_policy_times_out_and_drops() -> None:
    q = MemoryQueue(max_size=1, overflow_policy=OverflowPolicy.BLOCK, block_timeout=0.1)
    q.put(_event(1))
    start = time.monotonic()
    assert q.put(_event(2)) is False
    assert time.monotonic() - start >= 0.1
    assert q.dropped_count == 1


def test_invalid_overflow_policy_rejected() -> None:
    with pytest.raises(ValueError):
        MemoryQueue(max_size=10, overflow_policy="explode")


def test_invalid_max_size_rejected() -> None:
    with pytest.raises(ValueError):
        MemoryQueue(max_size=0)


def test_concurrent_puts_from_many_threads_never_lose_count() -> None:
    q = MemoryQueue(max_size=10_000, overflow_policy=OverflowPolicy.DROP_OLDEST)
    threads = [threading.Thread(target=lambda: q.put(_event(1))) for _ in range(500)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert q.qsize() == 500
