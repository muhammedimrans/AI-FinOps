"""
PersistentQueue — SQLite-backed durability checkpoint so telemetry
survives a process crash/restart, per the ticket's "When process crashes
-> Queue survives restart" requirement. Reuses the same design shape as
EP-17's `costorah_agent/queue/sqlite_store.py` (WAL mode, one row per
event, polled by `next_retry_at` for due-for-retry rows) — this is a
parallel, SDK-local implementation, not a shared import (the SDK does not
depend on the Monitoring Agent package).

Only ever touched from the BackgroundWorker's own thread — the SDK does
not open a second connection from the caller's thread, so there is no
cross-thread SQLite concurrency to reason about here.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from costorah.reliability._types import QueuedEvent

_SCHEMA = """
CREATE TABLE IF NOT EXISTS queued_events (
    id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    next_retry_at REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_queued_events_next_retry_at
    ON queued_events (next_retry_at);
"""


class PersistentQueue:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: the connection is constructed on the
        # caller's thread (BackgroundWorker.__init__) but exclusively used
        # from the worker's own thread thereafter — see worker.py's module
        # docstring. There is never truly concurrent access to it.
        self._conn = sqlite3.connect(
            str(self._path), isolation_level=None, check_same_thread=False
        )
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(_SCHEMA)
        self._closed = False

    def enqueue(self, event: QueuedEvent) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO queued_events (id, payload_json, attempts, created_at, "
            "next_retry_at) VALUES (?, ?, ?, ?, ?)",
            (event.event_id, json.dumps(event.payload), event.attempts, time.time(), 0.0),
        )

    def enqueue_many(self, events: list[QueuedEvent]) -> None:
        self._conn.executemany(
            "INSERT OR REPLACE INTO queued_events (id, payload_json, attempts, created_at, "
            "next_retry_at) VALUES (?, ?, ?, ?, ?)",
            [(e.event_id, json.dumps(e.payload), e.attempts, time.time(), 0.0) for e in events],
        )

    def dequeue_due(self, limit: int) -> list[QueuedEvent]:
        """Rows due for (re)delivery now, i.e. surviving events from a
        crash are picked up automatically the next time this runs — no
        separate startup-replay step is needed."""
        now = time.time()
        rows = self._conn.execute(
            "SELECT id, payload_json, attempts FROM queued_events "
            "WHERE next_retry_at <= ? ORDER BY created_at ASC LIMIT ?",
            (now, limit),
        ).fetchall()
        return [
            QueuedEvent(event_id=row[0], payload=json.loads(row[1]), attempts=row[2])
            for row in rows
        ]

    def mark_retry(self, event_id: str, *, attempts: int, next_retry_at: float) -> None:
        self._conn.execute(
            "UPDATE queued_events SET attempts = ?, next_retry_at = ? WHERE id = ?",
            (attempts, next_retry_at, event_id),
        )

    def ack(self, event_id: str) -> None:
        """Delivery succeeded (or the event was permanently rejected) —
        remove it."""
        self._conn.execute("DELETE FROM queued_events WHERE id = ?", (event_id,))

    def ack_many(self, event_ids: list[str]) -> None:
        self._conn.executemany(
            "DELETE FROM queued_events WHERE id = ?", [(i,) for i in event_ids]
        )

    def count(self) -> int:
        """Returns 0 (rather than raising) once `close()` has been
        called — health()/queue_stats() may still be queried by
        application code after `Costorah.shutdown()`, and reporting a
        stale-but-sane 0 is friendlier than surfacing a
        `sqlite3.ProgrammingError` for what is, from the caller's
        perspective, a perfectly normal state to introspect."""
        if self._closed:
            return 0
        row = self._conn.execute("SELECT COUNT(*) FROM queued_events").fetchone()
        return int(row[0])

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._conn.close()
