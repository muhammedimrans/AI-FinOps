from __future__ import annotations

import pytest

from costorah_agent.queue.retry import RetryPolicy


def test_default_backoff_sequence() -> None:
    policy = RetryPolicy()
    assert [policy.delay_for_attempt(n) for n in range(1, 8)] == [
        1.0,
        2.0,
        4.0,
        8.0,
        16.0,
        30.0,
        60.0,
    ]


def test_delay_clamps_at_last_value_once_exhausted() -> None:
    policy = RetryPolicy()
    assert policy.delay_for_attempt(8) == 60.0
    assert policy.delay_for_attempt(100) == 60.0


def test_delay_for_attempt_rejects_zero_or_negative() -> None:
    policy = RetryPolicy()
    with pytest.raises(ValueError):
        policy.delay_for_attempt(0)


def test_empty_backoff_seconds_rejected() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        RetryPolicy(backoff_seconds=[])


def test_non_positive_backoff_seconds_rejected() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        RetryPolicy(backoff_seconds=[1.0, 0.0])


def test_should_retry_forever_when_max_attempts_none() -> None:
    policy = RetryPolicy(max_attempts=None)
    assert policy.should_retry(1) is True
    assert policy.should_retry(10_000) is True


def test_should_retry_stops_at_max_attempts() -> None:
    policy = RetryPolicy(max_attempts=3)
    assert policy.should_retry(1) is True
    assert policy.should_retry(2) is True
    assert policy.should_retry(3) is False
    assert policy.should_retry(4) is False
