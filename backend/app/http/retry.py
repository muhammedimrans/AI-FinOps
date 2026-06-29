"""Concrete retry policy — F-033.

Implements the RetryPolicy ABC defined in EP-06 (F-030) so the abstract
interface drives the concrete behaviour without duplication.
"""

from __future__ import annotations

import random

from app.providers.errors import ProviderError
from app.providers.retry import BackoffStrategy, RetryConfig, RetryPolicy


class ExponentialRetryPolicy(RetryPolicy):
    """Exponential back-off with optional jitter.

    Retries only retryable ProviderError subclasses (RateLimitError,
    NetworkError, InternalProviderError).  Non-retryable errors (AuthenticationError,
    InvalidRequestError, QuotaExceededError) propagate immediately.
    """

    def __init__(self, config: RetryConfig | None = None) -> None:
        self._config = config or RetryConfig()

    def should_retry(self, attempt: int, error: Exception) -> bool:
        if attempt >= self._config.max_attempts:
            return False
        if isinstance(error, ProviderError):
            return error.retryable
        if self._config.retryable_error_types:
            return isinstance(error, tuple(self._config.retryable_error_types))
        return False

    def get_delay(self, attempt: int) -> float:
        cfg = self._config
        match cfg.backoff_strategy:
            case BackoffStrategy.FIXED:
                delay = cfg.initial_delay_seconds
            case BackoffStrategy.LINEAR:
                delay = cfg.initial_delay_seconds * attempt
            case BackoffStrategy.JITTER:
                base = cfg.initial_delay_seconds * (cfg.backoff_multiplier ** (attempt - 1))
                delay = base * (0.5 + random.random() * 0.5)  # noqa: S311
            case _:  # EXPONENTIAL (default)
                delay = cfg.initial_delay_seconds * (cfg.backoff_multiplier ** (attempt - 1))
        return min(delay, cfg.max_delay_seconds)

    def get_config(self) -> RetryConfig:
        return self._config
