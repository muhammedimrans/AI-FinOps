"""
RetryScheduler — exponential backoff with the ticket's exact default
schedule. Retries forever (no max-attempt cutoff) for transient failures,
matching the "at-least-once, never exactly-once" delivery guarantee — an
event is only ever removed from the queue by successful delivery, a
permanent rejection (see `is_retryable`), or overflow eviction.
"""

from __future__ import annotations

# Ticket's literal default schedule; holds at the last value thereafter.
DEFAULT_BACKOFF_SECONDS: tuple[float, ...] = (1, 2, 4, 8, 16, 30, 60, 120, 300)

_NEVER_RETRY = frozenset({400, 401, 403, 404})
_RETRYABLE = frozenset({408, 429, 500, 502, 503, 504})


def is_retryable(status_code: int | None) -> bool:
    """True for transient failures (network errors with no status code
    included) and the ticket's explicit retryable status list. False for
    permanent client errors — retrying an unchanged payload against those
    can never succeed."""
    if status_code is None:
        return True
    if status_code in _NEVER_RETRY:
        return False
    if status_code in _RETRYABLE:
        return True
    # Unlisted codes (e.g. a future 5xx) default to retryable — safer to
    # retry an unknown failure than to silently drop telemetry for it.
    return status_code >= 500


class RetryScheduler:
    def __init__(self, backoff_seconds: tuple[float, ...] = DEFAULT_BACKOFF_SECONDS) -> None:
        if not backoff_seconds:
            raise ValueError("backoff_seconds must not be empty")
        self._schedule = backoff_seconds

    def next_delay(self, attempt: int) -> float:
        """attempt is 1-indexed: the delay before retry #1 is
        next_delay(1)."""
        index = min(max(attempt, 1) - 1, len(self._schedule) - 1)
        return self._schedule[index]
