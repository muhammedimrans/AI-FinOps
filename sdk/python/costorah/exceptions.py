"""
SDK-specific exceptions. Every failure mode raised by `Costorah.track()`
is one of these — never a bare `httpx` exception or a raw HTTPStatusError,
so calling code can catch `costorah.AuthenticationError` etc. without
needing to know the SDK's HTTP library.

See `sdk/shared/API_CONTRACT.md` for the HTTP-status -> exception mapping
every COSTORAH SDK implements identically.
"""

from __future__ import annotations


class CostorahError(Exception):
    """Base class for every exception this SDK raises."""


class ConfigurationError(CostorahError):
    """Raised for invalid SDK configuration (e.g. a malformed API key)."""


class AuthenticationError(CostorahError):
    """401/403 from the ingestion API — invalid/expired key, suspended
    organization, or a key missing the `usage:write` scope. Not retried:
    this is a client configuration problem, not a transient failure."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ValidationError(CostorahError):
    """400/404/422 — the payload itself was rejected. Not retried: an
    unchanged payload can never succeed no matter how many times it's
    resent."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class RateLimitError(CostorahError):
    """429 — retried with backoff, honoring Retry-After if the server
    sends one."""

    def __init__(
        self, message: str, *, status_code: int | None = None, retry_after: float | None = None
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


class ServerError(CostorahError):
    """5xx from the ingestion API. Retried with exponential backoff."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class NetworkError(CostorahError):
    """No response was received at all (timeout, connection refused, DNS
    failure, TLS error, ...). Retried with exponential backoff."""
