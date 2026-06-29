"""Request telemetry — F-033.

Structured logging for every provider HTTP request.  Secret values (API keys,
auth headers) are never passed to this module — only metadata is logged.

The ``RequestTelemetry`` context manager measures wall-clock latency and emits
a structured log event on exit.  Hook points for future OpenTelemetry spans are
clearly marked.
"""

from __future__ import annotations

import time
import uuid

import structlog

logger = structlog.get_logger(__name__)


class RequestTelemetry:
    """Context manager that measures and logs a single HTTP request.

    Usage::

        with RequestTelemetry(method="GET", url=url, provider="openai") as tel:
            response = await client.get(url)
            tel.status_code = response.status_code
    """

    def __init__(self, *, method: str, url: str, provider: str) -> None:
        self.request_id = str(uuid.uuid4())
        self.method = method
        self.url = url
        self.provider = provider
        self.status_code: int = 0
        self.error: str | None = None
        self._start: float = 0.0
        self.latency_ms: float = 0.0

    def __enter__(self) -> RequestTelemetry:
        self._start = time.monotonic()
        # Future: start OpenTelemetry span here
        logger.debug(
            "provider_http_start",
            request_id=self.request_id,
            method=self.method,
            provider=self.provider,
        )
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.latency_ms = round((time.monotonic() - self._start) * 1000, 2)
        if exc_val is not None:
            self.error = type(exc_val).__name__

        if self.error:
            logger.warning(
                "provider_http_error",
                request_id=self.request_id,
                method=self.method,
                provider=self.provider,
                latency_ms=self.latency_ms,
                error=self.error,
            )
        else:
            logger.debug(
                "provider_http_done",
                request_id=self.request_id,
                method=self.method,
                provider=self.provider,
                status_code=self.status_code,
                latency_ms=self.latency_ms,
            )
        # Future: end OpenTelemetry span here
