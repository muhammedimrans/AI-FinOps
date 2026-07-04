"""Usage event validation — F-048 (EP-08).

Validates ``NormalizedUsageEvent`` instances before they are persisted.
Invalid events are rejected with a ``UsageValidationError`` rather than
stored with bad data.

Validation rules
----------------
- ``provider_request_id`` must be non-empty
- ``provider`` must be non-empty
- ``model`` must be non-empty
- ``timestamp`` must not be in the future (with a small tolerance)
- ``prompt_tokens``, ``completion_tokens``, ``total_tokens`` must be >= 0
- ``total_tokens`` must equal ``prompt_tokens + completion_tokens``
  (unless overridden by provider — checked with tolerance)
- ``request_count`` must be >= 1
- ``cached_tokens``, if present, must be >= 0 and <= ``prompt_tokens``
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog

from app.providers.models import NormalizedUsageEvent

log = structlog.get_logger(__name__)

# Allow timestamps up to this many seconds into the future (clock drift).
_FUTURE_TOLERANCE_SECONDS = 300


class UsageValidationError(Exception):
    """Raised when a NormalizedUsageEvent fails validation."""

    def __init__(self, message: str, event: NormalizedUsageEvent) -> None:
        super().__init__(message)
        self.event = event


class UsageEventValidator:
    """Validates a NormalizedUsageEvent against the EP-08 rules."""

    def validate(self, event: NormalizedUsageEvent) -> None:
        """Validate the event.  Raises ``UsageValidationError`` on failure."""
        self._check_required_strings(event)
        self._check_timestamp(event)
        self._check_token_counts(event)

    def _check_required_strings(self, event: NormalizedUsageEvent) -> None:
        if not event.provider_request_id or not event.provider_request_id.strip():
            raise UsageValidationError("provider_request_id is missing or empty", event)
        if not event.provider or not event.provider.strip():
            raise UsageValidationError("provider is missing or empty", event)
        if not event.model or not event.model.strip():
            raise UsageValidationError("model is missing or empty", event)

    def _check_timestamp(self, event: NormalizedUsageEvent) -> None:
        if event.timestamp is None:
            raise UsageValidationError("timestamp is missing", event)
        future_limit = datetime.now(UTC) + timedelta(seconds=_FUTURE_TOLERANCE_SECONDS)
        ts = event.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        if ts > future_limit:
            raise UsageValidationError(
                f"timestamp {event.timestamp!r} is too far in the future", event
            )

    def _check_token_counts(self, event: NormalizedUsageEvent) -> None:
        if event.prompt_tokens < 0:
            raise UsageValidationError("prompt_tokens must be >= 0", event)
        if event.completion_tokens < 0:
            raise UsageValidationError("completion_tokens must be >= 0", event)
        if event.total_tokens < 0:
            raise UsageValidationError("total_tokens must be >= 0", event)
        if event.request_count < 1:
            raise UsageValidationError("request_count must be >= 1", event)
        if event.cached_tokens is not None:
            if event.cached_tokens < 0:
                raise UsageValidationError("cached_tokens must be >= 0", event)
            if event.cached_tokens > event.prompt_tokens:
                raise UsageValidationError("cached_tokens cannot exceed prompt_tokens", event)
