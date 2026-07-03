from __future__ import annotations

import threading

import httpx

from costorah import Costorah


def test_end_to_end_track_success() -> None:
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
    assert result.usage_id == "u1"
    assert len(requests) == 1
    assert requests[0].headers["Authorization"] == "Bearer costorah_live_x"


def test_duplicate_response_surfaces_flag() -> None:
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
    result = client.track(provider="openai", model="gpt-4.1", cost=0.01)
    assert result.duplicate is True
    client.close()


def test_recovers_after_backend_outage_ends() -> None:
    """Failure recovery: a transient 503 outage followed by recovery
    should still yield a successful TrackResult from a single track()
    call, thanks to bounded retry (not a full offline queue — that's
    EP-18.3 — but track() itself must survive a brief blip)."""
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

    client = Costorah(
        api_key="costorah_live_x", max_retries=3, _transport=httpx.MockTransport(handler)
    )
    result = client.track(provider="openai", model="gpt-4.1", cost=0.01)
    assert result.success is True
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

    client.close()

    assert errors == []
    assert len(received_request_ids) == 50
    assert len(set(received_request_ids)) == 50  # no cross-contamination
    assert all(r is not None for r in results)
