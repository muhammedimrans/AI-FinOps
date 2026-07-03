from __future__ import annotations

from costorah.reliability.retry import DEFAULT_BACKOFF_SECONDS, RetryScheduler, is_retryable


def test_default_schedule_matches_ticket() -> None:
    assert DEFAULT_BACKOFF_SECONDS == (1, 2, 4, 8, 16, 30, 60, 120, 300)


def test_next_delay_follows_schedule() -> None:
    scheduler = RetryScheduler()
    assert scheduler.next_delay(1) == 1
    assert scheduler.next_delay(2) == 2
    assert scheduler.next_delay(3) == 4
    assert scheduler.next_delay(9) == 300


def test_next_delay_holds_at_last_value_beyond_schedule_length() -> None:
    scheduler = RetryScheduler()
    assert scheduler.next_delay(20) == 300
    assert scheduler.next_delay(1000) == 300


def test_next_delay_treats_zero_and_negative_as_first_attempt() -> None:
    scheduler = RetryScheduler()
    assert scheduler.next_delay(0) == 1
    assert scheduler.next_delay(-5) == 1


def test_never_retry_client_errors() -> None:
    for code in (400, 401, 403, 404):
        assert is_retryable(code) is False


def test_retry_transient_errors() -> None:
    for code in (408, 429, 500, 502, 503, 504):
        assert is_retryable(code) is True


def test_retry_network_error_with_no_status_code() -> None:
    assert is_retryable(None) is True


def test_retry_unknown_5xx_defaults_to_retryable() -> None:
    assert is_retryable(599) is True


def test_never_retry_unknown_4xx_defaults_to_not_retryable() -> None:
    assert is_retryable(418) is False
