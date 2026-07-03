from __future__ import annotations

import threading

import httpx

from costorah import Costorah


def test_end_to_end_track_success() -> None:
    """track() returns immediately (EP-18.3) — delivery is verified via
    flush() + the mock transport's captured requests, not via
    TrackResult's fields (which no longer carry the server's response)."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "success": True,
                "usage_id": "u1",
                "request_id": "sdk_py_test",
                "processed_at": "2026-01-01T00:00:00Z",
                "duplicate": False,
            },
        )

    with Costorah(api_key="costorah_live_x", _transport=httpx.MockTransport(handler)) as client:
        result = client.track(
            provider="anthropic",
            model="claude-sonnet-4",
            input_tokens=200,
            output_tokens=80,
            cost=0.012,
            latency_ms=410,
        )
        assert result.success is True
        assert result.queued is True
        assert client.flush(timeout=5) is True

    assert len(requests) == 1
    assert requests[0].headers["Authorization"] == "Bearer costorah_live_x"


def test_delivery_outcome_observable_via_queue_stats() -> None:
    """Since track() no longer surfaces the server's duplicate flag
    synchronously, delivery outcomes (including a duplicate response) are
    observable via queue_stats()'s sent_total after a flush instead."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "success": True,
                "usage_id": "u1",
                "request_id": "r1",
                "processed_at": "2026-01-01T00:00:00Z",
                "duplicate": True,
            },
        )

    client = Costorah(api_key="costorah_live_x", _transport=httpx.MockTransport(handler))
    client.track(provider="openai", model="gpt-4.1", cost=0.01)
    assert client.flush(timeout=5) is True
    assert client.queue_stats()["sent_total"] == 1
    client.close()


def test_recovers_after_backend_outage_ends() -> None:
    """Failure recovery: a transient 503 outage followed by recovery does
    not lose the event — the background worker retries with backoff
    (RetryScheduler's default schedule starts at 1s) until the backend
    recovers, all without track() itself ever blocking."""
    state = {"failures_left": 2}

    def handler(request: httpx.Request) -> httpx.Response:
        if state["failures_left"] > 0:
            state["failures_left"] -= 1
            return httpx.Response(503, json={"detail": "down"})
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

    client = Costorah(api_key="costorah_live_x", _transport=httpx.MockTransport(handler))
    result = client.track(provider="openai", model="gpt-4.1", cost=0.01)
    assert result.queued is True
    # Two 1s/2s backoff delays before the third (successful) attempt.
    assert client.flush(timeout=10) is True
    assert client.queue_stats()["sent_total"] == 1
    assert state["failures_left"] == 0
    client.close()


def test_concurrent_track_calls_from_multiple_threads_are_safe() -> None:
    """Thread safety: a single Costorah instance shared across threads
    must not corrupt or cross-contaminate requests."""
    received_request_ids: list[str] = []
    lock = threading.Lock()

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.content)
        with lock:
            received_request_ids.append(body["request_id"])
        return httpx.Response(
            200,
            json={
                "success": True,
                "usage_id": f"u_{body['request_id']}",
                "request_id": body["request_id"],
                "processed_at": "2026-01-01T00:00:00Z",
                "duplicate": False,
            },
        )

    client = Costorah(api_key="costorah_live_x", _transport=httpx.MockTransport(handler))
    results: list[object] = [None] * 50
    errors: list[Exception] = []

    def worker(index: int) -> None:
        try:
            results[index] = client.track(
                provider="openai", model="gpt-4.1", cost=0.001, request_id=f"thread-{index}"
            )
        except Exception as exc:  # pragma: no cover - failure path surfaced via assertion
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert client.flush(timeout=10) is True
    client.close()

    assert errors == []
    assert len(received_request_ids) == 50
    assert len(set(received_request_ids)) == 50  # no cross-contamination
    assert all(r is not None for r in results)
