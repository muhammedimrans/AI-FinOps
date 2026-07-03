"""
CostorahMiddleware — FastAPI/Starlette integration (EP-18.4).

    from fastapi import FastAPI
    from costorah.integrations.fastapi import CostorahMiddleware

    app = FastAPI()
    app.add_middleware(CostorahMiddleware)

With `COSTORAH_API_KEY` set in the environment, this is the entire
integration — no other setup. Per request, it:

  - Auto-initializes a `Costorah` client (once, at app startup) from
    `COSTORAH_API_KEY`/`COSTORAH_ENDPOINT`, or an explicit `api_key`/
    `client` passed to the middleware, and wires it as the default
    client every `costorah.instrumentation.*` instrumentor submits
    through (via `costorah.instrumentation.set_default_client`) —
    combine with e.g. `OpenAIInstrumentor().instrument()` at startup and
    every request handled through this app gets automatic usage
    tracking with zero per-request code.
  - Captures request context (a request ID — the incoming
    `X-Request-Id` header if present, otherwise a generated one — path,
    and method) and attaches it to every usage event captured during
    that request, under `metadata["request_context"]`.
  - Attaches `organization_id` (if configured) to that same context.
  - Echoes the request ID back via an `X-Costorah-Request-Id` response
    header, so a caller can correlate their request with the usage
    events it produced.

Entirely optional: an app that never adds this middleware behaves
exactly as it does today; instrumentation and manual `track()` calls
work identically with or without it.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Awaitable
from typing import TYPE_CHECKING, Any, Callable

from costorah._logging import get_logger
from costorah.context import request_context
from costorah.exceptions import CostorahError

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response
    from starlette.types import ASGIApp

    from costorah.client import Costorah

try:
    from starlette.middleware.base import BaseHTTPMiddleware
except ImportError as exc:  # pragma: no cover - exercised only without starlette installed
    raise ImportError(
        "costorah.integrations.fastapi requires 'fastapi' (or 'starlette') to be installed. "
        "Install it with `pip install fastapi` to use this integration."
    ) from exc

_log = get_logger(__name__)


class CostorahMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: ASGIApp,
        *,
        api_key: str | None = None,
        client: Costorah | None = None,
        organization_id: str | None = None,
    ) -> None:
        super().__init__(app)
        self._organization_id = organization_id
        self._client = client if client is not None else _auto_init_client(api_key)
        if self._client is not None:
            from costorah.instrumentation import set_default_client

            set_default_client(self._client)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("x-request-id") or f"req_{uuid.uuid4().hex}"
        context: dict[str, Any] = {
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
        }
        if self._organization_id:
            context["organization_id"] = self._organization_id

        with request_context(**context):
            response = await call_next(request)
        response.headers.setdefault("X-Costorah-Request-Id", request_id)
        return response


def _auto_init_client(api_key: str | None) -> Costorah | None:
    resolved_key = api_key or os.environ.get("COSTORAH_API_KEY")
    if not resolved_key:
        _log.warning(
            "costorah_middleware_no_api_key: set COSTORAH_API_KEY, or pass api_key=/client= "
            "to CostorahMiddleware — instrumentation will still capture usage locally "
            "(events_captured_total) but nothing will be submitted"
        )
        return None

    from costorah.client import Costorah

    try:
        endpoint = os.environ.get("COSTORAH_ENDPOINT", "https://api.costorah.com")
        return Costorah(api_key=resolved_key, endpoint=endpoint)
    except CostorahError as exc:
        _log.warning("costorah_middleware_init_failed error=%s", exc)
        return None
