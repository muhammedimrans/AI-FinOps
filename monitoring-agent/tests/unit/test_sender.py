from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from costorah_agent.queue.memory_queue import EventQueue
from costorah_agent.queue.retry import RetryPolicy
from costorah_agent.queue.sqlite_store import SQLiteEventStore
from costorah_agent.transport.http_client import IngestionOutcome, IngestionResult
from costorah_agent.transport.sender import Sender


class FakeHttpClient:
    """Duck-typed stand-in for HttpClient — returns queued outcomes in order."""

    def __init__(self, outcomes: list[IngestionResult]) -> None:
        self._outcomes = list(outcomes)
        self.sent_payloads: list[dict[str, Any]] = []

    async def send_usage_event(self, payload: dict[str, Any]) -> IngestionResult:
        self.sent_payloads.append(payload)
        return self._outcomes.pop(0)


@pytest.fixture
async def store(tmp_path: Path) -> SQLiteEventStore:
    s = SQLiteEventStore(tmp_path / "queue.db")
    yield s
    await s.close()


def _success(usage_id: str = "u1") -> IngestionResult:
    return IngestionResult(IngestionOutcome.SUCCESS, 200, "ingested", usage_id=usage_id)


def _duplicate() -> IngestionResult:
    return IngestionResult(IngestionOutcome.DUPLICATE, 200, "duplicate", usage_id="u1")


def _auth_failed() -> IngestionResult:
    return IngestionResult(IngestionOutcome.AUTH_FAILED, 401, "invalid key")


def _validation_failed() -> IngestionResult:
    return IngestionResult(IngestionOutcome.VALIDATION_FAILED, 400, "bad payload")


def _retryable() -> IngestionResult:
    return IngestionResult(IngestionOutcome.RETRYABLE_ERROR, 503, "server error")


async def test_run_once_delivers_success_and_removes_from_store(
    store: SQLiteEventStore,
) -> None:
    queue = EventQueue(max_size=10, overflow_store=store)
    await queue.put("evt_1", {"provider": "openai"})
    http = FakeHttpClient([_success()])
    sender = Sender(queue=queue, store=store, http_client=http, retry_policy=RetryPolicy())

    await sender.run_once()

    assert sender.metrics.events_sent_total == 1
    assert sender.metrics.uploads_total == 1
    assert await store.count() == 0


async def test_run_once_treats_duplicate_like_success(store: SQLiteEventStore) -> None:
    queue = EventQueue(max_size=10, overflow_store=store)
    await queue.put("evt_1", {"provider": "openai"})
    http = FakeHttpClient([_duplicate()])
    sender = Sender(queue=queue, store=store, http_client=http, retry_policy=RetryPolicy())

    await sender.run_once()

    assert sender.metrics.events_duplicate_total == 1
    assert sender.metrics.events_sent_total == 0
    assert await store.count() == 0


async def test_validation_failed_drops_event_permanently(store: SQLiteEventStore) -> None:
    queue = EventQueue(max_size=10, overflow_store=store)
    await queue.put("evt_1", {"provider": "openai"})
    http = FakeHttpClient([_validation_failed()])
    sender = Sender(queue=queue, store=store, http_client=http, retry_policy=RetryPolicy())

    await sender.run_once()

    assert sender.metrics.events_failed_total == 1
    assert await store.count() == 0  # dropped, not retried


async def test_retryable_error_persists_to_store_for_later_retry(
    store: SQLiteEventStore,
) -> None:
    queue = EventQueue(max_size=10, overflow_store=store)
    await queue.put("evt_1", {"provider": "openai"})
    http = FakeHttpClient([_retryable()])
    sender = Sender(queue=queue, store=store, http_client=http, retry_policy=RetryPolicy())

    await sender.run_once()

    assert sender.metrics.retries_total == 1
    assert await store.count() == 1  # kept for retry, not lost


async def test_auth_failed_persists_to_store_for_later_retry(store: SQLiteEventStore) -> None:
    queue = EventQueue(max_size=10, overflow_store=store)
    await queue.put("evt_1", {"provider": "openai"})
    http = FakeHttpClient([_auth_failed()])
    sender = Sender(queue=queue, store=store, http_client=http, retry_policy=RetryPolicy())

    await sender.run_once()

    assert sender.metrics.retries_total == 1
    assert await store.count() == 1


async def test_run_once_drains_due_retries_from_store(store: SQLiteEventStore) -> None:
    queue = EventQueue(max_size=10, overflow_store=store)
    await store.enqueue("evt_retry", {"provider": "openai"})
    http = FakeHttpClient([_success()])
    sender = Sender(queue=queue, store=store, http_client=http, retry_policy=RetryPolicy())

    await sender.run_once()

    assert sender.metrics.events_sent_total == 1
    assert await store.count() == 0


async def test_eventual_success_after_retry_removes_from_store(store: SQLiteEventStore) -> None:
    queue = EventQueue(max_size=10, overflow_store=store)
    await queue.put("evt_1", {"provider": "openai"})
    http = FakeHttpClient([_retryable(), _success()])
    sender = Sender(queue=queue, store=store, http_client=http, retry_policy=RetryPolicy())

    await sender.run_once()  # first attempt fails, persists to store
    assert await store.count() == 1

    # The real backoff delay hasn't elapsed yet, so it isn't due.
    assert await store.dequeue_due(limit=10) == []

    # Simulate elapsed backoff time by setting next_retry_at to now.
    await store.mark_failed("evt_1", datetime.now(UTC), "force-due")
    await sender.run_once()
    assert sender.metrics.events_sent_total == 1
    assert await store.count() == 0


async def test_metrics_track_provider_and_latency(store: SQLiteEventStore) -> None:
    queue = EventQueue(max_size=10, overflow_store=store)
    await queue.put("evt_1", {"provider": "openai"})
    http = FakeHttpClient([_success()])
    sender = Sender(queue=queue, store=store, http_client=http, retry_policy=RetryPolicy())

    await sender.run_once()

    assert sender.metrics.events_by_provider == {"openai": 1}
    assert sender.metrics.avg_latency_ms >= 0.0
    assert sender.metrics.last_upload_at is not None
