from __future__ import annotations

import time
import uuid

import structlog
from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = structlog.get_logger(__name__)


class RequestLoggingMiddleware:
    """
    Assigns a correlation ID to every request and logs method, path,
    status code, and wall-clock latency.

    Correlation ID:
    - Reads X-Request-ID from the incoming request if present.
    - Generates a new UUID4 otherwise.
    - Echoes the ID in the X-Request-ID response header.
    - Binds the ID into structlog contextvars so all log lines within
      the request automatically carry request_id.

    Implemented as raw ASGI middleware (not BaseHTTPMiddleware) so an
    unhandled exception deep in a route handler propagates and is turned
    into a response by Starlette's exception middleware immediately,
    rather than being caught in a response-streaming wrapper. Stacking
    BaseHTTPMiddleware subclasses is known to hang the connection when an
    exception occurs beneath them (the anyio stream used to relay the
    downstream response is never resolved) — see
    https://github.com/encode/starlette/discussions/1527.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id
            await send(message)

        start = time.monotonic()
        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            elapsed_ms = round((time.monotonic() - start) * 1000, 2)
            logger.error("request_failed", duration_ms=elapsed_ms)
            raise
        else:
            elapsed_ms = round((time.monotonic() - start) * 1000, 2)
            logger.info(
                "request_completed",
                status_code=status_code,
                duration_ms=elapsed_ms,
            )
        finally:
            structlog.contextvars.clear_contextvars()
