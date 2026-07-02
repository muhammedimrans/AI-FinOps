"""
RetryPolicy — exponential backoff schedule for failed uploads.

Default schedule: 1, 2, 4, 8, 16, 30, 60 seconds, then holds at the last
value (60s) for every subsequent attempt — this matches the sequence
given in the EP-17 spec exactly. `max_attempts=None` (the default) means
retry forever, which is what "never lose telemetry" requires: a durably
queued event is retried indefinitely until it either succeeds or an
operator explicitly intervenes, never silently dropped.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class RetryPolicy:
    backoff_seconds: list[float] = field(
        default_factory=lambda: [1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 60.0]
    )
    max_attempts: int | None = None

    def __post_init__(self) -> None:
        if not self.backoff_seconds:
            raise ValueError("backoff_seconds must not be empty")
        if any(v <= 0 for v in self.backoff_seconds):
            raise ValueError("backoff_seconds values must be positive")

    def delay_for_attempt(self, attempt: int) -> float:
        """
        Return the delay (seconds) before retry number `attempt`
        (1-indexed: the delay before the *first* retry, after the initial
        attempt, is delay_for_attempt(1)).
        """
        if attempt < 1:
            raise ValueError("attempt must be >= 1")
        index = min(attempt - 1, len(self.backoff_seconds) - 1)
        return self.backoff_seconds[index]

    def should_retry(self, attempt: int) -> bool:
        """Whether another attempt should be made after `attempt` failures."""
        if self.max_attempts is None:
            return True
        return attempt < self.max_attempts
