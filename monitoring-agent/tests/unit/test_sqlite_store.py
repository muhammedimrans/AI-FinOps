from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from costorah_agent.queue.sqlite_store import SQLiteEventStore


@pytest.fixture
async def store(tmp_path: Path) -> SQLiteEventStore:
    s = SQLiteEventStore(tmp_path / "queue.db")
    yield s
    await s.close()


async def test_enqueue_and_dequeue_due(store: SQLiteEventStore) -> None:
    await store.enqueue("evt_1", {"provider": "openai", "cost": 1.0})
    due = await store.dequeue_due()
    assert len(due) == 1
    assert due[0].id == "evt_1"
    assert due[0].payload == {"provider": "openai", "cost": 1.0}
    assert due[0].attempts == 0


async def test_enqueue_is_idempotent_on_duplicate_id(store: SQLiteEventStore) -> None:
    await store.enqueue("evt_1", {"cost": 1.0})
    await store.enqueue("evt_1", {"cost": 2.0})  # INSERT OR IGNORE: first write wins
    assert await store.count() == 1
    due = await store.dequeue_due()
    assert due[0].payload == {"cost": 1.0}


async def test_mark_failed_delays_next_retry(store: SQLiteEventStore) -> None:
    await store.enqueue("evt_1", {})
    future = datetime.now(UTC) + timedelta(hours=1)
    await store.mark_failed("evt_1", future, "connection refused")

    due = await store.dequeue_due()
    assert due == []  # not due yet
    assert await store.count() == 1  # still persisted, just not due


async def test_dequeue_due_only_returns_events_past_next_retry_at(
    store: SQLiteEventStore,
) -> None:
    await store.enqueue("evt_past", {})
    past = datetime.now(UTC) - timedelta(seconds=1)
    await store.mark_failed("evt_past", past, "err")

    await store.enqueue("evt_future", {})
    future = datetime.now(UTC) + timedelta(hours=1)
    await store.mark_failed("evt_future", future, "err")

    due = await store.dequeue_due(limit=100)
    assert [e.id for e in due] == ["evt_past"]
    assert due[0].attempts == 1


async def test_remove_deletes_event(store: SQLiteEventStore) -> None:
    await store.enqueue("evt_1", {})
    await store.remove("evt_1")
    assert await store.count() == 0


async def test_count_reflects_pending_events(store: SQLiteEventStore) -> None:
    assert await store.count() == 0
    await store.enqueue("evt_1", {})
    await store.enqueue("evt_2", {})
    assert await store.count() == 2


async def test_dequeue_due_respects_limit(store: SQLiteEventStore) -> None:
    for i in range(10):
        await store.enqueue(f"evt_{i}", {})
    due = await store.dequeue_due(limit=3)
    assert len(due) == 3


async def test_store_survives_reopen_same_path(tmp_path: Path) -> None:
    path = tmp_path / "queue.db"
    store1 = SQLiteEventStore(path)
    await store1.enqueue("evt_1", {"provider": "openai"})
    await store1.close()

    store2 = SQLiteEventStore(path)
    assert await store2.count() == 1
    await store2.close()
