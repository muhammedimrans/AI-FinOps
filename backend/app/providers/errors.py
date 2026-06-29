"""Provider error hierarchy — F-029."""

from __future__ import annotations


class ProviderError(Exception):
    """Base provider error."""

    def __init__(
        self,
        message: str,
        provider_type: str | None = None,
        *,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.provider_type = provider_type
        self.retryable = retryable


class RateLimitError(ProviderError):
    def __init__(
        self,
        message: str = "Rate limit exceeded",
        provider_type: str | None = None,
        *,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message, provider_type, retryable=True)
        self.retry_after_seconds = retry_after_seconds


class AuthenticationError(ProviderError):
    def __init__(
        self,
        message: str = "Authentication failed",
        provider_type: str | None = None,
    ) -> None:
        super().__init__(message, provider_type, retryable=False)


class NetworkError(ProviderError):
    def __init__(
        self,
        message: str = "Network error",
        provider_type: str | None = None,
    ) -> None:
        super().__init__(message, provider_type, retryable=True)


class QuotaExceededError(ProviderError):
    def __init__(
        self,
        message: str = "Quota exceeded",
        provider_type: str | None = None,
    ) -> None:
        super().__init__(message, provider_type, retryable=False)


class InvalidRequestError(ProviderError):
    def __init__(
        self,
        message: str = "Invalid request",
        provider_type: str | None = None,
    ) -> None:
        super().__init__(message, provider_type, retryable=False)


class InternalProviderError(ProviderError):
    def __init__(
        self,
        message: str = "Internal provider error",
        provider_type: str | None = None,
    ) -> None:
        super().__init__(message, provider_type, retryable=True)
