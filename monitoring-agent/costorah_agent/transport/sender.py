"""
Sender — orchestrates Memory Queue -> Retry Queue -> HTTP Sender.

Delivery policy per outcome:
  SUCCESS / DUPLICATE    -> done; removed from the durable store if it was
                            there (a retry that finally succeeds)
  RETRYABLE_ERROR         -> re-queued to SQLite with exponential backoff
                            (network errors, timeouts, 5xx)
  AUTH_FAILED (401/403)   -> re-queued to SQLite with exponential backoff,
                            logged loudly every attempt — likely a config
                            problem (wrong/revoked key), but "never lose
                            telemetry" means the agent keeps the data
                            rather than discarding it while an operator
                            fixes the key
  VALIDATION_FAILED       -> dropped (not retried) — retrying byte-identical
  (400/404/422)              malformed input forever cannot ever succeed and
                            would grow the durable store unboundedly;
                            logged loudly so the underlying collector bug
                            is visible
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from costorah_agent.queue.memory_queue import EventQueue
from costorah_agent.queue.retry import RetryPolicy
from costorah_agent.queue.sqlite_store import SQLiteEventStore
from costorah_agent.transport.http_client import HttpClient, IngestionOutcome

log = structlog.get_logger(__name__)


@dataclass(slots=True)
class SenderMetrics:
    events_sent_total: int = 0
    events_duplicate_total: int = 0
    events_failed_total: int = 0  # permanently dropped (validation errors)
    retries_total: int = 0
    uploads_total: int = 0  # HTTP attempts, success or not
    last_upload_at: datetime | None = None
    last_latency_ms: float = 0.0
    latency_ms_sum: float = 0.0
    latency_ms_count: int = 0
    events_by_provider: dict[str, int] = field(default_factory=dict)

    @property
    def avg_latency_ms(self) -> float:
        if self.latency_ms_count == 0:
            return 0.0
        return self.latency_ms_sum / self.latency_ms_count

    def record_upload(self, *, latency_ms: float, provider: str | None) -> None:
        self.uploads_total += 1
        self.last_upload_at = datetime.now(UTC)
        self.last_latency_ms = latency_ms
        self.latency_ms_sum += latency_ms
        self.latency_ms_count += 1
        if provider:
            self.events_by_provider[provider] = self.events_by_provider.get(provider, 0) + 1


class Sender:
    """Drains the memory queue and the durable retry store, delivering
    events via HttpClient and re-queuing failures per the policy above."""

    def __init__(
        self,
        *,
        queue: EventQueue,
        store: SQLiteEventStore,
        http_client: HttpClient,
        retry_policy: RetryPolicy,
        batch_size: int = 50,
    ) -> None:
        self._queue = queue
        self._store = store
        self._http_client = http_client
        self._retry_policy = retry_policy
        self._batch_size = batch_size
        self.metrics = SenderMetrics()

    async def run_once(self) -> None:
        """One pass: drain fresh events, then drain due retries."""
        await self._drain_memory_queue()
        await self._drain_due_retries()

    async def _drain_memory_queue(self) -> None:
        for item in self._queue.get_batch_nowait(self._batch_size):
            await self._attempt_delivery(item.event_id, item.payload, attempt=1)

    async def _drain_due_retries(self) -> None:
        due = await self._store.dequeue_due(limit=self._batch_size)
        for queued in due:
            await self._attempt_delivery(queued.id, queued.payload, attempt=queued.attempts + 1)

    async def _attempt_delivery(self, event_id: str, payload: dict[str, Any], attempt: int) -> None:
        provider = payload.get("provider")
        start = time.monotonic()
        result = await self._http_client.send_usage_event(payload)
        latency_ms = (time.monotonic() - start) * 1000
        self.metrics.record_upload(latency_ms=latency_ms, provider=provider)

        if result.outcome in (IngestionOutcome.SUCCESS, IngestionOutcome.DUPLICATE):
            if result.outcome == IngestionOutcome.SUCCESS:
                self.metrics.events_sent_total += 1
            else:
                self.metrics.events_duplicate_total += 1
            await self._store.remove(event_id)
            return

        if result.outcome == IngestionOutcome.VALIDATION_FAILED:
            self.metrics.events_failed_total += 1
            log.error(
                "usage_event_dropped_invalid",
                event_id=event_id,
                provider=provider,
                status_code=result.status_code,
                detail=result.detail,
            )
            await self._store.remove(event_id)
            return

        # AUTH_FAILED or RETRYABLE_ERROR: keep retrying.
        self.metrics.retries_total += 1
        log_fn = log.error if result.outcome == IngestionOutcome.AUTH_FAILED else log.warning
        log_fn(
            "usage_event_delivery_failed",
            event_id=event_id,
            provider=provider,
            outcome=result.outcome.value,
            status_code=result.status_code,
            detail=result.detail,
            attempt=attempt,
        )
        delay = self._retry_policy.delay_for_attempt(attempt)
        next_retry_at = datetime.now(UTC) + timedelta(seconds=delay)
        if attempt == 1:
            # First failure — this event was never in the durable store
            # (it came straight from the memory queue), so persist it now.
            await self._store.enqueue(event_id, payload)
        await self._store.mark_failed(event_id, next_retry_at, result.detail)
