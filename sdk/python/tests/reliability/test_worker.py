from __future__ import annotations

import threading
from pathlib import Path

import httpx

from costorah.config import Config
from costorah.reliability import (
    BackgroundWorker,
    ConnectionPool,
    OverflowPolicy,
    QueuedEvent,
)


def _success_response(request: httpx.Request) -> httpx.Response:
    import json

    body = json.loads(request.content)
    return httpx.Response(
        200,
        json={
            "success": True,
            "usage_id": "u1",
            "request_id": body["request_id"],
            "processed_at": "2026-01-01T00:00:00Z",
            "duplicate": False,
        },
    )


def _make_worker(handler: object, **kwargs: object) -> BackgroundWorker:
    config = Config(api_key="costorah_live_x", batch_size=kwargs.pop("batch_size", 10))
    pool = ConnectionPool(config, transport=httpx.MockTransport(handler))
    worker = BackgroundWorker(config, connection_pool=pool, **kwargs)
    worker.start()
    return worker


def test_events_delivered_and_acked() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return _success_response(request)

    worker = _make_worker(handler)
    for i in range(10):
        worker.submit(
            QueuedEvent(payload={"provider": "openai", "model": "m", "request_id": f"r{i}"})
        )
    assert worker.flush(timeout=5) is True
    assert len(calls) == 10
    worker.shutdown()


def test_permanent_failure_is_dropped_not_retried() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(401, json={"detail": "bad key"})

    worker = _make_worker(handler)
    worker.submit(QueuedEvent(payload={"provider": "openai", "model": "m", "request_id": "r1"}))
    assert worker.flush(timeout=5) is True
    worker.shutdown()
    assert len(calls) == 1  # never retried
    assert worker.metrics.snapshot()["failed_total"] == 1


def test_transient_failure_retried_until_success() -> None:
    state = {"remaining_failures": 2}

    def handler(request: httpx.Request) -> httpx.Response:
        if state["remaining_failures"] > 0:
            state["remaining_failures"] -= 1
            return httpx.Response(503, json={"detail": "down"})
        return _success_response(request)

    worker = _make_worker(handler)
    worker.submit(QueuedEvent(payload={"provider": "openai", "model": "m", "request_id": "r1"}))
    assert worker.flush(timeout=10) is True
    worker.shutdown()
    assert state["remaining_failures"] == 0
    assert worker.metrics.snapshot()["sent_total"] == 1
    assert worker.metrics.snapshot()["retry_count"] == 2


def test_retry_disabled_drops_on_first_transient_failure() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(503, json={"detail": "down"})

    worker = _make_worker(handler, retry_enabled=False)
    worker.submit(QueuedEvent(payload={"provider": "openai", "model": "m", "request_id": "r1"}))
    assert worker.flush(timeout=5) is True
    worker.shutdown()
    assert len(calls) == 1


def test_circuit_opens_and_stops_sending_then_recovers() -> None:
    state = {"fail": True}
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if state["fail"]:
            return httpx.Response(500, json={"detail": "down"})
        return _success_response(request)

    config = Config(api_key="costorah_live_x", batch_size=10)
    pool = ConnectionPool(config, transport=httpx.MockTransport(handler))
    worker = BackgroundWorker(config, connection_pool=pool)
    worker.circuit_breaker._failure_threshold = 2  # open quickly for the test
    worker.circuit_breaker._recovery_timeout = 0.1
    worker.start()

    for i in range(5):
        worker.submit(
            QueuedEvent(payload={"provider": "openai", "model": "m", "request_id": f"r{i}"})
        )

    # Wait for the circuit to open (2 failures observed).
    import time

    deadline = time.monotonic() + 5
    while worker.circuit_breaker.state == "closed" and time.monotonic() < deadline:
        time.sleep(0.02)
    assert worker.circuit_breaker.state == "open"

    state["fail"] = False
    assert worker.flush(timeout=10) is True
    worker.shutdown()
    assert worker.metrics.snapshot()["sent_total"] == 5


def test_dropped_newest_when_queue_overflows() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _success_response(request)

    config = Config(api_key="costorah_live_x", batch_size=1)
    pool = ConnectionPool(config, transport=httpx.MockTransport(handler))
    worker = BackgroundWorker(
        config,
        connection_pool=pool,
        queue_size=1,
        overflow_policy=OverflowPolicy.DROP_NEWEST,
        poll_interval=5.0,  # keep the worker from draining during the test
    )
    # Don't start() — verify overflow purely at the MemoryQueue level
    # without racing the background drain.
    assert worker.submit(QueuedEvent(payload={"n": 1})) is True
    assert worker.submit(QueuedEvent(payload={"n": 2})) is False
    assert worker.memory_queue.dropped_count == 1


def test_survives_restart_with_real_persistent_queue_file(tmp_path: Path) -> None:
    """Crash recovery: events written to a real on-disk persistent queue
    file are picked up by a *new* BackgroundWorker pointed at the same
    file — simulating the application restarting after a crash."""
    path = tmp_path / "queue.db"
    calls: list[httpx.Request] = []

    def always_down(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(503, json={"detail": "down"})

    config = Config(api_key="costorah_live_x", batch_size=10)
    pool1 = ConnectionPool(config, transport=httpx.MockTransport(always_down))
    worker1 = BackgroundWorker(config, connection_pool=pool1, persistent_queue_path=str(path))
    worker1.start()
    worker1.submit(
        QueuedEvent(
            event_id="crash-1",
            payload={"provider": "openai", "model": "m", "request_id": "r1"},
        )
    )
    # Give it one pass to persist the event, then simulate a crash: stop
    # the thread without a graceful flush/drain.
    import time

    time.sleep(0.3)
    worker1._stop_event.set()
    if worker1._thread:
        worker1._thread.join(timeout=2)
    assert worker1.persistent_queue is not None
    assert worker1.persistent_queue.count() == 1
    worker1.persistent_queue.close()

    def now_succeeds(request: httpx.Request) -> httpx.Response:
        return _success_response(request)

    pool2 = ConnectionPool(config, transport=httpx.MockTransport(now_succeeds))
    worker2 = BackgroundWorker(config, connection_pool=pool2, persistent_queue_path=str(path))
    worker2.start()
    assert worker2.flush(timeout=5) is True
    worker2.shutdown()


def test_compression_applied_for_large_metadata_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        # Body is gzip-compressed here (large metadata) — don't try to
        # json.loads() it directly like _success_response does; a canned
        # response is enough to verify compression + delivery.
        return httpx.Response(
            200,
            json={
                "success": True,
                "usage_id": "u1",
                "request_id": "r1",
                "processed_at": "2026-01-01T00:00:00Z",
                "duplicate": False,
            },
        )

    worker = _make_worker(handler, compression_enabled=True)
    worker.submit(
        QueuedEvent(
            payload={
                "provider": "openai",
                "model": "m",
                "request_id": "r1",
                "metadata": {"blob": "x" * 5000},
            }
        )
    )
    assert worker.flush(timeout=5) is True
    worker.shutdown()
    assert worker.metrics.snapshot()["compression_ratio"] is not None
    assert worker.metrics.snapshot()["compression_ratio"] < 1.0


def test_compression_disabled_never_sets_content_encoding() -> None:
    received_headers: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        received_headers.append(dict(request.headers))
        return _success_response(request)

    worker = _make_worker(handler, compression_enabled=False)
    worker.submit(
        QueuedEvent(
            payload={
                "provider": "openai",
                "model": "m",
                "request_id": "r1",
                "metadata": {"blob": "x" * 5000},
            }
        )
    )
    assert worker.flush(timeout=5) is True
    worker.shutdown()
    assert "content-encoding" not in received_headers[0]


def test_concurrent_submit_from_many_threads() -> None:
    calls: list[httpx.Request] = []
    lock = threading.Lock()

    def handler(request: httpx.Request) -> httpx.Response:
        with lock:
            calls.append(request)
        return _success_response(request)

    worker = _make_worker(handler, batch_size=25)
    threads = [
        threading.Thread(
            target=lambda i=i: worker.submit(
                QueuedEvent(payload={"provider": "openai", "model": "m", "request_id": f"r{i}"})
            )
        )
        for i in range(200)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert worker.flush(timeout=15) is True
    worker.shutdown()
    assert len(calls) == 200
