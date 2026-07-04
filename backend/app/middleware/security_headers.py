"""Security response headers for the JSON API.

The frontend is a separately-hosted SPA (Cloudflare Pages); this API serves
JSON only, so the header set is tuned for an API origin:

- ``Strict-Transport-Security`` — only added in production, where the API is
  always behind TLS; emitting it on plain-HTTP local dev would be wrong.
- ``Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`` —
  an API never needs to load subresources or be framed; this neutralises any
  reflected-content vector if a response is ever rendered by a browser.
- ``X-Content-Type-Options: nosniff`` — prevents MIME sniffing of JSON.
- ``X-Frame-Options: DENY`` — legacy equivalent of frame-ancestors.
- ``Referrer-Policy: no-referrer`` — API responses never need referrers.
- ``Permissions-Policy`` — no browser features are used by API responses.
- ``Cache-Control: no-store`` is set only for /v1/auth/* responses so tokens
  are never cached by intermediaries; data endpoints keep their own caching.

Implemented as raw ASGI middleware (not BaseHTTPMiddleware) — see the
docstring in request_logging.py for why: stacking BaseHTTPMiddleware
subclasses hangs the connection when an unhandled exception occurs beneath
them, instead of letting Starlette's exception handling produce a response.
"""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class SecurityHeadersMiddleware:
    """Attach standard security headers to every response."""

    def __init__(self, app: ASGIApp, *, hsts: bool = False) -> None:
        self.app = app
        self._hsts = hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("X-Frame-Options", "DENY")
                headers.setdefault("Referrer-Policy", "no-referrer")
                headers.setdefault(
                    "Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'"
                )
                headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
                if self._hsts:
                    headers.setdefault(
                        "Strict-Transport-Security", "max-age=63072000; includeSubDomains"
                    )
                if path.startswith("/v1/auth/"):
                    headers.setdefault("Cache-Control", "no-store")
            await send(message)

        await self.app(scope, receive, send_wrapper)
