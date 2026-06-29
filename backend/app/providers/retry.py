"""Retry policy interfaces — F-030."""

from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class BackoffStrategy(enum.StrEnum):
    FIXED = "fixed"
    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    JITTER = "jitter"


@dataclass(frozen=True, slots=True)
class RetryConfig:
    max_attempts: int = 3
    initial_delay_seconds: float = 1.0
    max_delay_seconds: float = 60.0
    backoff_strategy: BackoffStrategy = BackoffStrategy.EXPONENTIAL
    backoff_multiplier: float = 2.0
    retryable_error_types: frozenset[type[Exception]] = field(default_factory=frozenset)


class RetryPolicy(ABC):
    @abstractmethod
    def should_retry(self, attempt: int, error: Exception) -> bool: ...

    @abstractmethod
    def get_delay(self, attempt: int) -> float: ...

    @abstractmethod
    def get_config(self) -> RetryConfig: ...


class CircuitBreakerState(enum.StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker(ABC):
    @abstractmethod
    def get_state(self) -> CircuitBreakerState: ...

    @abstractmethod
    def record_success(self) -> None: ...

    @abstractmethod
    def record_failure(self) -> None: ...

    @abstractmethod
    def can_execute(self) -> bool: ...
