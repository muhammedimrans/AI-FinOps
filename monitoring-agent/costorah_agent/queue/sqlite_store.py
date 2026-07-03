"""
SQLiteEventStore — durable offline persistence for undelivered usage events.

This is what makes "never lose telemetry" true across process restarts and
extended COSTORAH outages: any event that can't be delivered immediately
is written here before the in-memory copy is discarded, and reloaded on
the next `dequeue_due()` call (including after the agent process itself
restarts, since this is a file on disk, not memory).

sqlite3 is synchronous; every call here runs on a worker thread via
`asyncio.to_thread` so it never blocks the event loop, keeping the agent's
collection/health/metrics coroutines responsive even under heavy retry
load (the 10,000-event performance test exercises this directly).
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS queued_events (
    id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_retry_at TEXT NOT NULL,
    last_error TEXT
);
CREATE INDEX IF NOT EXISTS ix_queued_events_next_retry ON queued_events(next_retry_at);
"""


@dataclass(slots=True)
class QueuedEvent:
    id: str
    payload: dict[str, Any]
    attempts: int
    created_at: datetime


class SQLiteEventStore:
    """Durable, file-backed queue of events pending (re)delivery."""

    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        self._conn: sqlite3.Connection | None = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            conn = sqlite3.connect(self._path, check_same_thread=False)
            conn.executescript(_SCHEMA)
            conn.commit()
            self._conn = conn
        return self._conn

    async def enqueue(self, event_id: str, payload: dict[str, Any]) -> None:
        await asyncio.to_thread(self._enqueue_sync, event_id, payload)

    def _enqueue_sync(self, event_id: str, payload: dict[str, Any]) -> None:
        conn = self._get_conn()
        now = datetime.now(UTC).isoformat()
        conn.execute(
            "INSERT OR IGNORE INTO queued_events "
            "(id, payload_json, created_at, attempts, next_retry_at) "
            "VALUES (?, ?, ?, 0, ?)",
            (event_id, json.dumps(payload), now, now),
        )
        conn.commit()

    async def dequeue_due(self, limit: int = 100) -> list[QueuedEvent]:
        return await asyncio.to_thread(self._dequeue_due_sync, limit)

    def _dequeue_due_sync(self, limit: int) -> list[QueuedEvent]:
        conn = self._get_conn()
        now = datetime.now(UTC).isoformat()
        rows = conn.execute(
            "SELECT id, payload_json, attempts, created_at FROM queued_events "
            "WHERE next_retry_at <= ? ORDER BY created_at ASC LIMIT ?",
            (now, limit),
        ).fetchall()
        return [
            QueuedEvent(
                id=row[0],
                payload=json.loads(row[1]),
                attempts=row[2],
                created_at=datetime.fromisoformat(row[3]),
            )
            for row in rows
        ]

    async def mark_failed(self, event_id: str, next_retry_at: datetime, error: str) -> None:
        await asyncio.to_thread(self._mark_failed_sync, event_id, next_retry_at, error)

    def _mark_failed_sync(self, event_id: str, next_retry_at: datetime, error: str) -> None:
        conn = self._get_conn()
        conn.execute(
            "UPDATE queued_events SET attempts = attempts + 1, "
            "next_retry_at = ?, last_error = ? WHERE id = ?",
            (next_retry_at.isoformat(), error[:1000], event_id),
        )
        conn.commit()

    async def remove(self, event_id: str) -> None:
        await asyncio.to_thread(self._remove_sync, event_id)

    def _remove_sync(self, event_id: str) -> None:
        conn = self._get_conn()
        conn.execute("DELETE FROM queued_events WHERE id = ?", (event_id,))
        conn.commit()

    async def count(self) -> int:
        return await asyncio.to_thread(self._count_sync)

    def _count_sync(self) -> int:
        conn = self._get_conn()
        row = conn.execute("SELECT COUNT(*) FROM queued_events").fetchone()
        return int(row[0])

    async def close(self) -> None:
        await asyncio.to_thread(self._close_sync)

    def _close_sync(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
