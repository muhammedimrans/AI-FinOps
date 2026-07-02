from __future__ import annotations

from pathlib import Path

import pytest

from costorah_agent.queue.memory_queue import EventQueue
from costorah_agent.queue.sqlite_store import SQLiteEventStore


@pytest.fixture
async def store(tmp_path: Path) -> SQLiteEventStore:
    s = SQLiteEventStore(tmp_path / "queue.db")
    yield s
    await s.close()


async def test_put_and_get_batch(store: SQLiteEventStore) -> None:
    queue = EventQueue(max_size=10, overflow_store=store)
    await queue.put("evt_1", {"provider": "openai"})
    await queue.put("evt_2", {"provider": "anthropic"})

    assert queue.qsize() == 2
    batch = queue.get_batch_nowait(10)
    assert [item.event_id for item in batch] == ["evt_1", "evt_2"]
    assert queue.qsize() == 0


async def test_get_batch_nowait_respects_max_items(store: SQLiteEventStore) -> None:
    queue = EventQueue(max_size=10, overflow_store=store)
    for i in range(5):
        await queue.put(f"evt_{i}", {})

    batch = queue.get_batch_nowait(3)
    assert len(batch) == 3
    assert queue.qsize() == 2


async def test_get_batch_nowait_empty_returns_empty_list(store: SQLiteEventStore) -> None:
    queue = EventQueue(max_size=10, overflow_store=store)
    assert queue.get_batch_nowait(5) == []


async def test_put_overflows_to_disk_when_full(store: SQLiteEventStore) -> None:
    queue = EventQueue(max_size=2, overflow_store=store)
    await queue.put("evt_1", {"n": 1})
    await queue.put("evt_2", {"n": 2})
    await queue.put("evt_3", {"n": 3})  # overflow: memory queue is full

    assert queue.qsize() == 2
    assert queue.overflowed_total == 1
    assert await store.count() == 1

    due = await store.dequeue_due()
    assert [e.id for e in due] == ["evt_3"]
