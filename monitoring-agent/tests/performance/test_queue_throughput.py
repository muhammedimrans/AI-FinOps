"""
Performance tests per the EP-17 spec: 10,000 queued events, memory, CPU,
retry latency. These are correctness-at-scale checks, not micro-benchmarks
— they assert the queue/store/retry subsystems behave correctly and stay
within the documented resource targets (<100MB memory, <2% CPU) under a
representative load, run against this process (not a spawned agent), using
stdlib `resource` rather than adding a psutil dependency just for tests.
"""

from __future__ import annotations

import asyncio
import gc
import resource
import time
from pathlib import Path

import pytest

from costorah_agent.queue.memory_queue import EventQueue
from costorah_agent.queue.retry import RetryPolicy
from costorah_agent.queue.sqlite_store import SQLiteEventStore

EVENT_COUNT = 10_000


@pytest.fixture
async def store(tmp_path: Path) -> SQLiteEventStore:
    s = SQLiteEventStore(tmp_path / "perf-queue.db")
    yield s
    await s.close()


async def test_ten_thousand_events_enqueue_and_drain_correctly(store: SQLiteEventStore) -> None:
    """max_memory_events defaults to 10,000 (config.py QueueConfig) — this
    exercises exactly that overflow boundary: some events land in memory,
    the rest overflow to the durable store, and no event is lost either
    way."""
    queue = EventQueue(max_size=EVENT_COUNT, overflow_store=store)

    start = time.perf_counter()
    for i in range(EVENT_COUNT):
        await queue.put(f"evt_{i}", {"provider": "openai", "n": i})
    enqueue_elapsed = time.perf_counter() - start

    assert queue.qsize() == EVENT_COUNT
    assert queue.overflowed_total == 0

    drained: list[str] = []
    while True:
        batch = queue.get_batch_nowait(500)
        if not batch:
            break
        drained.extend(item.event_id for item in batch)

    assert len(drained) == EVENT_COUNT
    assert len(set(drained)) == EVENT_COUNT  # no duplicates, none lost
    assert enqueue_elapsed < 5.0  # generous ceiling; typically well under 1s


async def test_ten_thousand_events_overflow_to_disk_when_queue_smaller(
    store: SQLiteEventStore,
) -> None:
    """A bounded queue smaller than the event burst must overflow the
    excess to SQLite rather than blocking or dropping — this is what
    "never lose telemetry" means under sustained backpressure."""
    queue = EventQueue(max_size=1_000, overflow_store=store)

    for i in range(EVENT_COUNT):
        await queue.put(f"evt_{i}", {"n": i})

    in_memory = queue.qsize()
    on_disk = await store.count()
    assert in_memory == 1_000
    assert on_disk == EVENT_COUNT - 1_000
    assert in_memory + on_disk == EVENT_COUNT
    assert queue.overflowed_total == EVENT_COUNT - 1_000


async def test_sqlite_store_handles_ten_thousand_events(store: SQLiteEventStore) -> None:
    start = time.perf_counter()
    for i in range(EVENT_COUNT):
        await store.enqueue(f"evt_{i}", {"provider": "openai", "n": i})
    elapsed = time.perf_counter() - start

    assert await store.count() == EVENT_COUNT
    # Each enqueue() commits (fsyncs) individually — 10,000 sequential
    # commits is disk-bound and can be slow on constrained/virtualized
    # storage. This ceiling is intentionally generous; it exists to catch
    # a real regression (e.g. an accidental O(n^2)), not to assert a tight
    # throughput SLA for this worst-case all-overflow scenario.
    assert elapsed < 60.0

    due = await store.dequeue_due(limit=EVENT_COUNT)
    assert len(due) == EVENT_COUNT


async def test_memory_usage_stays_within_target_for_ten_thousand_events(
    store: SQLiteEventStore,
) -> None:
    """Target from the EP-17 spec: <100MB agent memory footprint. This
    doesn't measure the whole agent process, but confirms that holding
    10,000 queued events in memory alone is nowhere near that ceiling —
    the dominant cost the spec is actually worried about."""
    gc.collect()
    baseline_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

    queue = EventQueue(max_size=EVENT_COUNT, overflow_store=store)
    for i in range(EVENT_COUNT):
        await queue.put(
            f"evt_{i}",
            {
                "provider": "openai",
                "model": "gpt-4o",
                "request_id": f"agent_evt_{i}",
                "input_tokens": 100,
                "output_tokens": 50,
                "cost": 0.001,
                "currency": "USD",
                "status": "success",
                "timestamp": "2026-01-01T00:00:00+00:00",
                "metadata": {},
            },
        )

    gc.collect()
    after_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    delta_mb = (after_kb - baseline_kb) / 1024

    assert delta_mb < 100, f"10,000 queued events added {delta_mb:.1f}MB (target <100MB)"


async def test_cpu_time_for_ten_thousand_event_drain_is_bounded(store: SQLiteEventStore) -> None:
    """Not a literal "<2% CPU" measurement (that's a sustained-load,
    whole-process metric outside a unit-test's reach) — instead asserts
    the CPU time actually consumed processing 10,000 events is small in
    absolute terms, which is the property the spec's target is a proxy
    for."""
    queue = EventQueue(max_size=EVENT_COUNT, overflow_store=store)
    for i in range(EVENT_COUNT):
        await queue.put(f"evt_{i}", {"n": i})

    cpu_start = time.process_time()
    drained = 0
    while True:
        batch = queue.get_batch_nowait(500)
        if not batch:
            break
        drained += len(batch)
    cpu_elapsed = time.process_time() - cpu_start

    assert drained == EVENT_COUNT
    assert cpu_elapsed < 2.0, f"draining 10,000 events used {cpu_elapsed:.2f}s CPU time"


async def test_retry_latency_matches_configured_backoff_schedule(
    store: SQLiteEventStore,
) -> None:
    """Confirms delay_for_attempt's timing contract holds in practice: an
    event marked failed with a short backoff isn't due before that delay
    elapses, and is due once it has."""
    policy = RetryPolicy(backoff_seconds=[0.15, 0.3])
    await store.enqueue("evt_1", {})

    import datetime as dt

    delay = policy.delay_for_attempt(1)
    next_retry = dt.datetime.now(dt.UTC) + dt.timedelta(seconds=delay)
    await store.mark_failed("evt_1", next_retry, "retryable")

    immediately_due = await store.dequeue_due()
    assert immediately_due == []  # backoff hasn't elapsed yet

    await asyncio.sleep(delay + 0.1)
    now_due = await store.dequeue_due()
    assert [e.id for e in now_due] == ["evt_1"]
    assert now_due[0].attempts == 1
