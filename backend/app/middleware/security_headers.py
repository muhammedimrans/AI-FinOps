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
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach standard security headers to every response."""

    def __init__(self, app: object, *, hsts: bool = False) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._hsts = hsts

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)

        headers = response.headers
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", "no-referrer")
        headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")

        if self._hsts:
            headers.setdefault(
                "Strict-Transport-Security", "max-age=63072000; includeSubDomains"
            )

        if request.url.path.startswith("/v1/auth/"):
            headers.setdefault("Cache-Control", "no-store")

        return response
