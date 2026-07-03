"""
BackgroundWorker — ties every reliability component together, per the
ticket's pipeline:

    Memory Queue -> Background Worker -> Persistent Queue -> Compression
    -> Retry Engine -> Circuit Breaker -> Connection Pool -> Usage API

Runs on a dedicated thread with its own asyncio event loop, so
`Costorah.track()` (called from arbitrary application threads) never
touches the network — it only ever pushes into `MemoryQueue`, an O(1),
lock-protected operation.

Batch upload, honestly documented: EP-16's `POST /v1/ingest/usage`
ingestion endpoint (the "Usage API" node in the ticket's diagram) accepts
exactly one usage record per request — there is no multi-event batch
endpoint, and adding one would mean modifying a previous Engineering
Package's API surface, which the ticket says not to do unless absolutely
necessary. "Batching" here means what it can honestly mean without that:
the worker groups up to `batch_size` due events per pass and delivers
them concurrently (bounded by `max_connections`) over the pooled
connection, instead of one blocking round trip at a time — real
throughput improvement, but still one HTTP request per event, not fewer
HTTP requests than events.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time

from costorah._logging import get_logger
from costorah.config import Config
from costorah.reliability._types import OverflowPolicy, QueuedEvent
from costorah.reliability.circuit_breaker import CircuitBreaker
from costorah.reliability.compression import compression_ratio, maybe_compress
from costorah.reliability.connection_pool import ConnectionPool
from costorah.reliability.memory_queue import MemoryQueue
from costorah.reliability.metrics import BackpressureController, TelemetryMetrics
from costorah.reliability.persistent_queue import PersistentQueue
from costorah.reliability.retry import RetryScheduler, is_retryable

_log = get_logger(__name__)

_INGEST_PATH = "/v1/ingest/usage"


class BackgroundWorker:
    def __init__(
        self,
        config: Config,
        *,
        queue_size: int = 10_000,
        overflow_policy: str = OverflowPolicy.DROP_OLDEST,
        persistent_queue_path: str = ":memory:",
        compression_enabled: bool = True,
        retry_enabled: bool = True,
        poll_interval: float = 0.2,
        max_concurrent_deliveries: int = 10,
        connection_pool: ConnectionPool | None = None,
    ) -> None:
        self._config = config
        self.memory_queue = MemoryQueue(max_size=queue_size, overflow_policy=overflow_policy)
        self.persistent_queue: PersistentQueue | None = PersistentQueue(persistent_queue_path)
        self.compression_enabled = compression_enabled
        self._retry_enabled = retry_enabled
        self.retry_scheduler = RetryScheduler()
        self.circuit_breaker = CircuitBreaker()
        self.metrics = TelemetryMetrics()
        self.backpressure = BackpressureController()
        self._pool = connection_pool or ConnectionPool(config)
        self._owns_pool = connection_pool is None
        self._poll_interval = poll_interval
        self._batch_size = config.batch_size
        self._max_concurrent = max_concurrent_deliveries

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop_event.clear()
        self.backpressure.set_worker_status("running")
        self._thread = threading.Thread(
            target=self._thread_main, daemon=True, name="costorah-worker"
        )
        self._thread.start()

    def _thread_main(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._run())
        finally:
            if self._owns_pool:
                loop.run_until_complete(self._pool.aclose())
            loop.close()

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            drained = await self._pass()
            if not drained:
                await asyncio.sleep(self._poll_interval)
        # Final best-effort drain on shutdown.
        await self._pass()

    async def _pass(self) -> bool:
        """One iteration: drain memory queue into persistence, then
        attempt delivery of anything due. Returns True if any work was
        done (so the caller can avoid sleeping unnecessarily)."""
        assert self.persistent_queue is not None
        did_work = False

        batch = self.memory_queue.get_batch(self._batch_size)
        if batch:
            self.persistent_queue.enqueue_many(batch)
            did_work = True

        if self.circuit_breaker.state == "open":
            return did_work

        due = self.persistent_queue.dequeue_due(self._batch_size)
        if not due:
            return did_work

        semaphore = asyncio.Semaphore(self._max_concurrent)

        async def deliver_bounded(event: QueuedEvent) -> None:
            async with semaphore:
                await self._deliver_one(event)

        await asyncio.gather(*(deliver_bounded(e) for e in due))
        return True

    async def _deliver_one(self, event: QueuedEvent) -> None:
        assert self.persistent_queue is not None
        if not self.circuit_breaker.allow_request():
            return

        body = json.dumps(event.payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.compression_enabled:
            compressed, was_compressed = maybe_compress(body)
            if was_compressed:
                self.metrics.record_compression(compression_ratio(len(body), len(compressed)))
                headers["Content-Encoding"] = "gzip"
                body = compressed

        start = time.perf_counter()
        try:
            response = await self._pool.post(_INGEST_PATH, content=body, headers=headers)
        except Exception as exc:  # network error: httpx.TransportError/TimeoutException et al.
            self._on_failure(event, status_code=None, detail=str(exc), start=start)
            return

        elapsed_ms = (time.perf_counter() - start) * 1000
        if response.status_code == 200:
            self.circuit_breaker.record_success()
            self.persistent_queue.ack(event.event_id)
            self.metrics.record_upload(latency_ms=elapsed_ms, batch_size=1, success=True)
            return

        self._on_failure(
            event, status_code=response.status_code, detail=response.text[:200], start=start
        )

    def _on_failure(
        self, event: QueuedEvent, *, status_code: int | None, detail: str, start: float
    ) -> None:
        elapsed_ms = (time.perf_counter() - start) * 1000
        self.metrics.record_upload(latency_ms=elapsed_ms, batch_size=1, success=False)
        assert self.persistent_queue is not None

        if not self._retry_enabled or not is_retryable(status_code):
            # Permanent failure (400/401/403/404) or retry disabled by
            # config — drop it. An unchanged payload retried against a
            # 4xx can never succeed; logging is the only remaining record.
            self.persistent_queue.ack(event.event_id)
            _log.warning(
                "costorah: dropping event after permanent failure status=%s detail=%s",
                status_code,
                detail,
            )
            return

        self.circuit_breaker.record_failure()
        self.metrics.record_retry()
        attempts = event.attempts + 1
        delay = self.retry_scheduler.next_delay(attempts)
        self.persistent_queue.mark_retry(
            event.event_id, attempts=attempts, next_retry_at=time.time() + delay
        )
        _log.warning(
            "costorah: retrying event after %s (attempt %s, next retry in %.1fs)",
            status_code or "network error",
            attempts,
            delay,
        )

    def submit(self, event: QueuedEvent) -> bool:
        return self.memory_queue.put(event)

    def flush(self, timeout: float = 10.0) -> bool:
        """Blocks until the memory + persistent queues are drained, or
        `timeout` elapses. Returns True if fully drained."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            assert self.persistent_queue is not None
            if self.memory_queue.is_empty() and self.persistent_queue.count() == 0:
                return True
            time.sleep(0.05)
        return self.memory_queue.is_empty() and (
            self.persistent_queue.count() == 0 if self.persistent_queue else True
        )

    def shutdown(self, timeout: float = 10.0) -> None:
        """Graceful shutdown: flush what can be flushed, then stop the
        worker thread. Safe to call more than once."""
        if self._thread is None:
            return
        self.flush(timeout=timeout)
        self.backpressure.set_worker_status("stopped")
        self._stop_event.set()
        self._thread.join(timeout=timeout)
        if self.persistent_queue is not None:
            self.persistent_queue.close()
        self._thread = None
