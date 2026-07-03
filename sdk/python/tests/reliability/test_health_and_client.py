from __future__ import annotations

import json

import httpx

from costorah import Costorah


def _instant_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
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

    return httpx.MockTransport(handler)


def test_health_matches_ticket_shape() -> None:
    client = Costorah(api_key="costorah_live_x", _transport=_instant_transport())
    health = client.health()
    assert set(health.keys()) == {"worker", "queue_depth", "retry_queue", "circuit", "compression"}
    assert health["worker"] == "running"
    assert health["circuit"] == "closed"
    assert health["compression"] == "enabled"
    client.close()
    assert client.health()["worker"] == "stopped"


def test_health_compression_disabled_reflected() -> None:
    client = Costorah(api_key="costorah_live_x", compression=False, _transport=_instant_transport())
    assert client.health()["compression"] == "disabled"
    client.close()


def test_queue_stats_reflects_activity() -> None:
    client = Costorah(api_key="costorah_live_x", _transport=_instant_transport())
    for i in range(5):
        client.track(provider="openai", model="m", cost=0.0, request_id=f"r{i}")
    assert client.flush(timeout=5) is True
    stats = client.queue_stats()
    assert stats["sent_total"] == 5
    assert stats["queue_depth"] == 0
    assert stats["worker_status"] == "running"
    client.close()


def test_track_returns_immediately_under_1ms() -> None:
    import time

    client = Costorah(api_key="costorah_live_x", _transport=_instant_transport())
    # Warm up.
    for _ in range(20):
        client.track(provider="openai", model="m", cost=0.0)

    samples = []
    for _ in range(200):
        start = time.perf_counter()
        client.track(provider="openai", model="m", cost=0.0)
        samples.append((time.perf_counter() - start) * 1000)
    avg_ms = sum(samples) / len(samples)
    client.close()
    assert avg_ms < 1.0, f"average track() took {avg_ms:.4f}ms (target <1ms)"


def test_100000_queued_events_no_blocking() -> None:
    """Performance target: 100,000 queued events, no UI/application
    blocking. track() itself must stay fast throughout — verified by
    bounding total wall time for 100k enqueue calls alone (not delivery,
    which happens off the critical path)."""
    import time

    client = Costorah(
        api_key="costorah_live_x", queue_size=200_000, _transport=_instant_transport()
    )
    start = time.perf_counter()
    for i in range(100_000):
        result = client.track(provider="openai", model="m", cost=0.0001, request_id=f"perf-{i}")
        assert result.success is True
    elapsed = time.perf_counter() - start
    assert elapsed < 10.0, f"100,000 track() calls took {elapsed:.2f}s (target: fast, non-blocking)"
    client.close()


def test_memory_stays_within_target_for_100000_events() -> None:
    import gc
    import resource

    client = Costorah(
        api_key="costorah_live_x", queue_size=200_000, _transport=_instant_transport()
    )
    gc.collect()
    baseline_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

    for i in range(100_000):
        client.track(provider="openai", model="m", cost=0.0001, request_id=f"mem-{i}")
    client.close()

    gc.collect()
    after_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    delta_mb = (after_kb - baseline_kb) / 1024
    assert delta_mb < 100, f"100,000 track() calls added {delta_mb:.1f}MB (target <100MB)"
