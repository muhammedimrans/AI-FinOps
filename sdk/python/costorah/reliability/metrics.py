"""
TelemetryMetrics and BackpressureController — the counters/gauges the
ticket's SDK Health API and Telemetry Metrics sections require. Kept as
one small module: both are thin, thread-safe accumulators with no
behavior beyond bookkeeping (the actual overflow *policy* lives in
MemoryQueue; BackpressureController just aggregates the numbers every
component reports into a single stats snapshot).
"""

from __future__ import annotations

import threading
import time


class TelemetryMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._retry_count = 0
        self._upload_latencies_ms: list[float] = []
        self._last_compression_ratio: float | None = None
        self._last_batch_size = 0
        self._sent_total = 0
        self._failed_total = 0
        self._started_at = time.monotonic()

    def record_retry(self) -> None:
        with self._lock:
            self._retry_count += 1

    def record_upload(self, *, latency_ms: float, batch_size: int, success: bool) -> None:
        with self._lock:
            self._upload_latencies_ms.append(latency_ms)
            # Bounded rolling window — never grows unbounded over a
            # long-lived process.
            if len(self._upload_latencies_ms) > 1000:
                self._upload_latencies_ms = self._upload_latencies_ms[-1000:]
            self._last_batch_size = batch_size
            if success:
                self._sent_total += batch_size
            else:
                self._failed_total += batch_size

    def record_compression(self, ratio: float) -> None:
        with self._lock:
            self._last_compression_ratio = ratio

    @property
    def worker_uptime_seconds(self) -> float:
        return time.monotonic() - self._started_at

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            avg_latency = (
                sum(self._upload_latencies_ms) / len(self._upload_latencies_ms)
                if self._upload_latencies_ms
                else 0.0
            )
            return {
                "sent_total": self._sent_total,
                "failed_total": self._failed_total,
                "retry_count": self._retry_count,
                "avg_upload_latency_ms": round(avg_latency, 2),
                "compression_ratio": self._last_compression_ratio,
                "last_batch_size": self._last_batch_size,
                "worker_uptime_seconds": round(self.worker_uptime_seconds, 1),
            }


class BackpressureController:
    """Aggregates queue/worker state into the exact stats shape the
    ticket's Backpressure and SDK Health API sections ask for."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._worker_status = "stopped"

    def set_worker_status(self, status: str) -> None:
        with self._lock:
            self._worker_status = status

    @property
    def worker_status(self) -> str:
        with self._lock:
            return self._worker_status
