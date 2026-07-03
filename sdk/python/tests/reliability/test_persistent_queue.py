from __future__ import annotations

import tempfile
import time
from pathlib import Path

from costorah.reliability import PersistentQueue, QueuedEvent


def test_enqueue_and_dequeue_due_immediately() -> None:
    q = PersistentQueue(":memory:")
    q.enqueue(QueuedEvent(event_id="e1", payload={"n": 1}))
    due = q.dequeue_due(10)
    assert len(due) == 1
    assert due[0].event_id == "e1"
    assert due[0].payload == {"n": 1}


def test_mark_retry_delays_future_dequeue() -> None:
    q = PersistentQueue(":memory:")
    q.enqueue(QueuedEvent(event_id="e1", payload={}))
    q.mark_retry("e1", attempts=1, next_retry_at=time.time() + 10)
    assert q.dequeue_due(10) == []
    assert q.count() == 1


def test_ack_removes_event() -> None:
    q = PersistentQueue(":memory:")
    q.enqueue(QueuedEvent(event_id="e1", payload={}))
    assert q.count() == 1
    q.ack("e1")
    assert q.count() == 0


def test_enqueue_many_and_ack_many() -> None:
    q = PersistentQueue(":memory:")
    events = [QueuedEvent(event_id=f"e{i}", payload={"n": i}) for i in range(20)]
    q.enqueue_many(events)
    assert q.count() == 20
    q.ack_many([f"e{i}" for i in range(10)])
    assert q.count() == 10


def test_dequeue_due_orders_by_created_at() -> None:
    q = PersistentQueue(":memory:")
    for i in range(5):
        q.enqueue(QueuedEvent(event_id=f"e{i}", payload={"n": i}))
    due = q.dequeue_due(5)
    assert [e.event_id for e in due] == [f"e{i}" for i in range(5)]


def test_survives_process_restart_via_real_file() -> None:
    """Crash recovery: a real on-disk file (not :memory:) still has
    unacked events after the PersistentQueue object is dropped and a new
    one is opened against the same path — simulating a process
    restart."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "queue.db"
        q1 = PersistentQueue(path)
        q1.enqueue(QueuedEvent(event_id="e1", payload={"n": 1}))
        q1.close()  # simulates process exit without a clean drain

        q2 = PersistentQueue(path)
        due = q2.dequeue_due(10)
        assert len(due) == 1
        assert due[0].event_id == "e1"
        q2.close()


def test_corrupt_queue_file_raises_on_open_not_silently_loses_data(tmp_path: Path) -> None:
    """A genuinely corrupt SQLite file fails loudly at open time (sqlite3
    raises DatabaseError) rather than silently starting empty — the
    caller (BackgroundWorker construction) surfaces this instead of
    masking data loss."""
    import sqlite3

    bad_path = tmp_path / "corrupt.db"
    bad_path.write_bytes(b"this is not a sqlite database")

    with __import__("pytest").raises(sqlite3.DatabaseError):
        PersistentQueue(bad_path)  # schema creation runs at construction time
