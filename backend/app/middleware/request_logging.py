from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Assigns a correlation ID to every request and logs method, path,
    status code, and wall-clock latency.

    Correlation ID:
    - Reads X-Request-ID from the incoming request if present.
    - Generates a new UUID4 otherwise.
    - Echoes the ID in the X-Request-ID response header.
    - Binds the ID into structlog contextvars so all log lines within
      the request automatically carry request_id.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        start = time.monotonic()

        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = round((time.monotonic() - start) * 1000, 2)
            logger.error(
                "request_failed",
                duration_ms=elapsed_ms,
            )
            raise
        finally:
            structlog.contextvars.clear_contextvars()

        elapsed_ms = round((time.monotonic() - start) * 1000, 2)

        logger.info(
            "request_completed",
            status_code=response.status_code,
            duration_ms=elapsed_ms,
        )

        response.headers["X-Request-ID"] = request_id
        return response
