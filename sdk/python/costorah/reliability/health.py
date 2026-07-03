"""
HealthMonitor — formats the exact `client.health()` shape from the
ticket:

    {
      "worker": "running",
      "queue_depth": 24,
      "retry_queue": 3,
      "circuit": "closed",
      "compression": "enabled"
    }
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from costorah.reliability.worker import BackgroundWorker


class HealthMonitor:
    def __init__(self, worker: BackgroundWorker) -> None:
        self._worker = worker

    def snapshot(self) -> dict[str, Any]:
        w = self._worker
        return {
            "worker": w.backpressure.worker_status,
            "queue_depth": w.memory_queue.qsize(),
            "retry_queue": w.persistent_queue.count() if w.persistent_queue else 0,
            "circuit": w.circuit_breaker.state,
            "compression": "enabled" if w.compression_enabled else "disabled",
        }

    def queue_stats(self) -> dict[str, Any]:
        w = self._worker
        return {
            "queue_depth": w.memory_queue.qsize(),
            "dropped_events": w.memory_queue.dropped_count,
            "retry_queue_size": w.persistent_queue.count() if w.persistent_queue else 0,
            "worker_status": w.backpressure.worker_status,
            **w.metrics.snapshot(),
        }
