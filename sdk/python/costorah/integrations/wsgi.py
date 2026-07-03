"""
CostorahWSGIMiddleware — generic WSGI integration (EP-18.5).

    from costorah.integrations.wsgi import CostorahWSGIMiddleware

    app = CostorahWSGIMiddleware(app)

A raw WSGI middleware with no dependency on any specific framework —
suitable for Bottle, Pyramid, or any other WSGI-compatible application
(including Flask, though `costorah.integrations.flask.CostorahExtension`
is preferred there since it wires up Flask's application-factory and
multi-app patterns natively — internally, it wraps `app.wsgi_app` with
this same class). Behaves identically to the other integrations:
auto-initializes a client from `COSTORAH_API_KEY`, captures request
context (request ID, path, method, optional organization ID) via
`costorah.context`, and echoes the request ID back via an
`X-Costorah-Request-Id` response header.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any

from costorah.context import request_context
from costorah.integrations._common import auto_init_client, generate_request_id

if TYPE_CHECKING:
    from costorah.client import Costorah

WSGIEnviron = dict[str, Any]
StartResponse = Callable[..., Any]
WSGIApp = Callable[[WSGIEnviron, StartResponse], Iterable[bytes]]


class CostorahWSGIMiddleware:
    def __init__(
        self,
        app: WSGIApp,
        *,
        api_key: str | None = None,
        client: Costorah | None = None,
        organization_id: str | None = None,
    ) -> None:
        self.app = app
        self._organization_id = organization_id
        self._client = (
            client if client is not None else auto_init_client(api_key, integration_name="wsgi")
        )
        if self._client is not None:
            from costorah.instrumentation import set_default_client

            set_default_client(self._client)

    def __call__(self, environ: WSGIEnviron, start_response: StartResponse) -> Iterable[bytes]:
        request_id = environ.get("HTTP_X_REQUEST_ID") or generate_request_id()
        context: dict[str, Any] = {
            "request_id": request_id,
            "path": environ.get("PATH_INFO", ""),
            "method": environ.get("REQUEST_METHOD", ""),
        }
        if self._organization_id:
            context["organization_id"] = self._organization_id

        def start_response_with_header(
            status: str, headers: list[tuple[str, str]], exc_info: object = None
        ) -> Any:
            headers = [*headers, ("X-Costorah-Request-Id", request_id)]
            return start_response(status, headers, exc_info)

        with request_context(**context):
            return self.app(environ, start_response_with_header)
