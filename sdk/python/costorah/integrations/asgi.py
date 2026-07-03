"""
CostorahASGIMiddleware — generic ASGI integration (EP-18.5).

    from costorah.integrations.asgi import CostorahASGIMiddleware

    app = CostorahASGIMiddleware(app)

A raw ASGI 3 middleware with no dependency on any specific framework —
suitable for Quart, Falcon, Litestar, or any other ASGI-compatible
application (including FastAPI/Starlette, though
`costorah.integrations.fastapi`/`.starlette` are preferred there since
they're request/response-aware and integrate more natively). Behaves
identically to the FastAPI/Starlette middleware: auto-initializes a
client from `COSTORAH_API_KEY`, captures request context (request ID,
path, method, optional organization ID) via `costorah.context`, and
echoes the request ID back via an `X-Costorah-Request-Id` response
header. Non-HTTP scopes (`lifespan`, `websocket`) pass through
untouched — no context is attached to them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from costorah.context import request_context
from costorah.integrations._common import auto_init_client, generate_request_id

if TYPE_CHECKING:
    from costorah.client import Costorah

# Minimal ASGI type aliases — kept local rather than imported from any
# framework, since the whole point of this module is zero framework
# dependency.
Scope = dict[str, Any]
Message = dict[str, Any]
Receive = Any
Send = Any
ASGIApp = Any


class CostorahASGIMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        api_key: str | None = None,
        client: Costorah | None = None,
        organization_id: str | None = None,
    ) -> None:
        self.app = app
        self._organization_id = organization_id
        self._client = (
            client if client is not None else auto_init_client(api_key, integration_name="asgi")
        )
        if self._client is not None:
            from costorah.instrumentation import set_default_client

            set_default_client(self._client)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        request_id = headers.get(b"x-request-id", b"").decode() or generate_request_id()
        context: dict[str, Any] = {
            "request_id": request_id,
            "path": scope.get("path", ""),
            "method": scope.get("method", ""),
        }
        if self._organization_id:
            context["organization_id"] = self._organization_id

        async def send_with_header(message: Message) -> None:
            if message.get("type") == "http.response.start":
                response_headers = list(message.get("headers") or [])
                response_headers.append((b"x-costorah-request-id", request_id.encode()))
                message = {**message, "headers": response_headers}
            await send(message)

        with request_context(**context):
            await self.app(scope, receive, send_with_header)
