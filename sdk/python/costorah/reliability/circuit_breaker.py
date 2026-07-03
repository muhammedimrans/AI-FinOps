"""
CircuitBreaker — stops sending after repeated failures, probes
periodically, recovers automatically. Standard three-state design
(Closed/Open/Half-Open); EP-17's Monitoring Agent has no circuit breaker
of its own to reuse (confirmed: no circuit/breaker concept anywhere in
that package) — this is net-new for EP-18.3.
"""

from __future__ import annotations

import threading
import time


class CircuitState:
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 1,
    ) -> None:
        if failure_threshold <= 0:
            raise ValueError("failure_threshold must be positive")
        if half_open_max_calls <= 0:
            raise ValueError("half_open_max_calls must be positive")
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max_calls = half_open_max_calls

        self._lock = threading.Lock()
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._opened_at: float | None = None
        self._half_open_calls_in_flight = 0
        self._half_open_successes = 0

    @property
    def state(self) -> str:
        with self._lock:
            return self._current_state_locked()

    def _current_state_locked(self) -> str:
        if (
            self._state == CircuitState.OPEN
            and self._opened_at is not None
            and time.monotonic() - self._opened_at >= self._recovery_timeout
        ):
            self._state = CircuitState.HALF_OPEN
            self._half_open_calls_in_flight = 0
            self._half_open_successes = 0
        return self._state

    def allow_request(self) -> bool:
        """Call before attempting delivery. False means: don't send, keep
        the event queued for a later pass."""
        with self._lock:
            state = self._current_state_locked()
            if state == CircuitState.CLOSED:
                return True
            if state == CircuitState.OPEN:
                return False
            # HALF_OPEN: allow a bounded number of probe calls through.
            if self._half_open_calls_in_flight < self._half_open_max_calls:
                self._half_open_calls_in_flight += 1
                return True
            return False

    def record_success(self) -> None:
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._half_open_successes += 1
                if self._half_open_successes >= self._half_open_max_calls:
                    self._state = CircuitState.CLOSED
                    self._consecutive_failures = 0
                    self._opened_at = None
            else:
                self._consecutive_failures = 0

    def record_failure(self) -> None:
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                # Probe failed — reopen immediately.
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()
                self._half_open_calls_in_flight = 0
                self._half_open_successes = 0
                return
            self._consecutive_failures += 1
            if self._consecutive_failures >= self._failure_threshold:
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()
