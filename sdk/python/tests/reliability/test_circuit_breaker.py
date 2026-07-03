from __future__ import annotations

import time

from costorah.reliability import CircuitBreaker, CircuitState


def test_starts_closed() -> None:
    cb = CircuitBreaker()
    assert cb.state == CircuitState.CLOSED
    assert cb.allow_request() is True


def test_opens_after_failure_threshold() -> None:
    cb = CircuitBreaker(failure_threshold=3)
    for _ in range(2):
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.allow_request() is False


def test_success_resets_failure_count() -> None:
    cb = CircuitBreaker(failure_threshold=3)
    cb.record_failure()
    cb.record_failure()
    cb.record_success()
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.CLOSED  # only 2 consecutive since reset


def test_transitions_to_half_open_after_recovery_timeout() -> None:
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.05)
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    time.sleep(0.06)
    assert cb.state == CircuitState.HALF_OPEN


def test_half_open_probe_success_closes_circuit() -> None:
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.05, half_open_max_calls=1)
    cb.record_failure()
    time.sleep(0.06)
    assert cb.allow_request() is True  # the probe call
    cb.record_success()
    assert cb.state == CircuitState.CLOSED


def test_half_open_probe_failure_reopens_circuit() -> None:
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.05, half_open_max_calls=1)
    cb.record_failure()
    time.sleep(0.06)
    assert cb.allow_request() is True
    cb.record_failure()
    assert cb.state == CircuitState.OPEN


def test_half_open_bounds_concurrent_probes() -> None:
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.05, half_open_max_calls=1)
    cb.record_failure()
    time.sleep(0.06)
    assert cb.allow_request() is True  # consumes the one allowed probe
    assert cb.allow_request() is False  # a second concurrent call is rejected
