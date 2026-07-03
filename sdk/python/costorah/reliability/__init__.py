"""
COSTORAH SDK reliability layer (EP-18.3): background delivery, queueing,
retry, circuit breaking, and compression so `track()` never blocks the
application on network I/O. See `sdk/docs/RELIABILITY.md`.
"""

from __future__ import annotations

from costorah.reliability._types import OverflowPolicy, QueuedEvent
from costorah.reliability.circuit_breaker import CircuitBreaker, CircuitState
from costorah.reliability.compression import maybe_compress
from costorah.reliability.connection_pool import ConnectionPool
from costorah.reliability.health import HealthMonitor
from costorah.reliability.memory_queue import MemoryQueue
from costorah.reliability.metrics import BackpressureController, TelemetryMetrics
from costorah.reliability.persistent_queue import PersistentQueue
from costorah.reliability.retry import DEFAULT_BACKOFF_SECONDS, RetryScheduler, is_retryable
from costorah.reliability.worker import BackgroundWorker

__all__ = [
    "DEFAULT_BACKOFF_SECONDS",
    "BackgroundWorker",
    "BackpressureController",
    "CircuitBreaker",
    "CircuitState",
    "ConnectionPool",
    "HealthMonitor",
    "MemoryQueue",
    "OverflowPolicy",
    "PersistentQueue",
    "QueuedEvent",
    "RetryScheduler",
    "TelemetryMetrics",
    "is_retryable",
    "maybe_compress",
]
