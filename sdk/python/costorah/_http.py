"""
HTTP transport: POSTs to COSTORAH's Usage Ingestion API (EP-16),
authenticated via an Organization API Key (EP-15), with bounded
exponential-backoff retry for transient failures.

Retry is bounded (`config.max_retries`, default 3) because `track()` is a
synchronous, blocking call in this phase (EP-18.1) — a caller's request
handler is waiting on it. EP-17's Monitoring Agent retries forever because
it owns a background process with nothing else to block; an SDK call
embedded in application code does not have that luxury. Unbounded,
queued, non-blocking retry is EP-18.3 scope (see `sdk/shared/API_CONTRACT.md`).
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from costorah._logging import get_logger
from costorah.config import Config
from costorah.exceptions import (
    AuthenticationError,
    NetworkError,
    RateLimitError,
    ServerError,
    ValidationError,
)
from costorah.version import __version__

_INGEST_PATH = "/v1/ingest/usage"

# Matches EP-17's RetryPolicy exactly, for consistency across the
# COSTORAH ecosystem (sdk/shared/API_CONTRACT.md).
_BACKOFF_SECONDS = (1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 60.0)

_log = get_logger(__name__)


def _backoff_delay(attempt: int) -> float:
    """attempt is 1-indexed: the delay before retry #1 is _backoff_delay(1)."""
    index = min(attempt - 1, len(_BACKOFF_SECONDS) - 1)
    return _BACKOFF_SECONDS[index]


def _safe_detail(response: httpx.Response) -> str:
    """Extract a short error detail without ever echoing the full response
    body (which could contain caller-supplied metadata) into an exception
    message or log line."""
    try:
        body = response.json()
        detail = body.get("detail")
        if isinstance(detail, str):
            return detail[:500]
    except ValueError:
        pass
    return f"HTTP {response.status_code}"


class HttpTransport:
    """Thin synchronous wrapper around the EP-16 ingestion endpoint."""

    def __init__(self, config: Config, *, transport: httpx.BaseTransport | None = None) -> None:
        self._config = config
        self._client = httpx.Client(
            base_url=config.endpoint,
            timeout=config.timeout,
            verify=config.verify_tls,
            transport=transport,
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
                "User-Agent": f"costorah-python/{__version__}",
            },
        )

    def post_usage_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST one usage event, retrying transient failures with
        exponential backoff up to `config.max_retries` times. Raises a
        costorah.* exception on any non-recoverable or exhausted-retry
        outcome — never a bare httpx exception."""
        attempt = 0
        while True:
            attempt += 1
            try:
                response = self._client.post(_INGEST_PATH, json=payload)
            except httpx.TimeoutException as exc:
                self._retry_or_raise(NetworkError(f"request timed out: {exc}"), attempt)
                continue
            except httpx.TransportError as exc:
                self._retry_or_raise(NetworkError(f"connection error: {exc}"), attempt)
                continue

            outcome = self._handle_response(response, attempt)
            if outcome is not None:
                return outcome
            # else: _handle_response already slept for the retry backoff.

    def _handle_response(self, response: httpx.Response, attempt: int) -> dict[str, Any] | None:
        if response.status_code == 200:
            return dict(response.json())
        if response.status_code in (401, 403):
            raise AuthenticationError(_safe_detail(response), status_code=response.status_code)
        if response.status_code in (400, 404, 422):
            raise ValidationError(_safe_detail(response), status_code=response.status_code)
        if response.status_code == 429:
            retry_after = _parse_retry_after(response)
            self._retry_or_raise(
                RateLimitError(
                    _safe_detail(response),
                    status_code=429,
                    retry_after=retry_after,
                ),
                attempt,
                delay_override=retry_after,
            )
            return None
        if response.status_code >= 500:
            self._retry_or_raise(
                ServerError(_safe_detail(response), status_code=response.status_code), attempt
            )
            return None
        # Any other unexpected status: surface as a ServerError rather than
        # silently succeeding or retrying forever on something unknown.
        raise ServerError(
            f"unexpected status {response.status_code}: {_safe_detail(response)}",
            status_code=response.status_code,
        )

    def _retry_or_raise(
        self,
        error: NetworkError | RateLimitError | ServerError,
        attempt: int,
        *,
        delay_override: float | None = None,
    ) -> None:
        if attempt > self._config.max_retries:
            raise error
        delay = delay_override if delay_override is not None else _backoff_delay(attempt)
        _log.warning(
            "costorah: retrying after %s (attempt %s/%s, sleeping %.1fs)",
            type(error).__name__,
            attempt,
            self._config.max_retries,
            delay,
        )
        time.sleep(delay)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HttpTransport:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


def _parse_retry_after(response: httpx.Response) -> float | None:
    header = response.headers.get("Retry-After")
    if header is None:
        return None
    try:
        return float(header)
    except ValueError:
        return None
