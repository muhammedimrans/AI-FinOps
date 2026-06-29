"""Shared provider HTTP client — F-033.

ProviderHttpClient wraps HttpxTransport and adds:

* Per-request UUIDs injected as ``X-Request-ID`` (never logged with secret values)
* Structured request/response telemetry via RequestTelemetry
* Automatic HTTP error → ProviderError normalization (F-039)
* Injectable mock_transport for hermetic unit testing

Security invariants
-------------------
* Auth headers are built by HttpAuth strategies — the credential string is
  passed in at construction time but is never written to any log line.
* ``User-Agent`` identifies the platform version without leaking credentials.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx

from app.http.auth import HttpAuth
from app.http.telemetry import RequestTelemetry
from app.http.transport import HttpxTransport
from app.providers.errors import (
    AuthenticationError,
    InternalProviderError,
    InvalidRequestError,
    NetworkError,
    ProviderError,
    RateLimitError,
)

_USER_AGENT = "aifinops/0.1.0 (provider-integration)"


def _parse_retry_after(response: httpx.Response) -> float | None:
    raw = response.headers.get("Retry-After") or response.headers.get("retry-after")
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def map_http_error(response: httpx.Response, *, provider_type: str) -> ProviderError:
    """Convert an unsuccessful HTTP response to the appropriate ProviderError (F-039)."""
    match response.status_code:
        case 401:
            return AuthenticationError(
                "Invalid API key or unauthorized", provider_type=provider_type
            )
        case 403:
            return AuthenticationError(
                "Access forbidden — check API key permissions or org settings",
                provider_type=provider_type,
            )
        case 404:
            return InvalidRequestError(
                f"Endpoint not found: {response.url}", provider_type=provider_type
            )
        case 408 | 504:
            return NetworkError("Request timed out", provider_type=provider_type)
        case 429:
            return RateLimitError(
                "Rate limit exceeded",
                provider_type=provider_type,
                retry_after_seconds=_parse_retry_after(response),
            )
        case 500 | 502 | 503:
            return InternalProviderError(
                f"Provider server error ({response.status_code})",
                provider_type=provider_type,
            )
        case _:
            return ProviderError(
                f"Unexpected HTTP {response.status_code}",
                provider_type=provider_type,
            )


class ProviderHttpClient:
    """Async HTTP client used by all provider adapters.

    Pass *mock_transport* (an ``httpx.AsyncBaseTransport``) to bypass real
    network calls in unit tests::

        transport = httpx.MockTransport(handler=my_handler)
        client = ProviderHttpClient(
            base_url="https://api.openai.com",
            auth=BearerTokenAuth(key),
            provider_type="openai",
            mock_transport=transport,
        )
    """

    def __init__(
        self,
        *,
        base_url: str,
        auth: HttpAuth,
        provider_type: str,
        timeout: float = 30.0,
        mock_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url
        self._auth = auth
        self._provider_type = provider_type
        self._timeout = timeout
        self._transport = HttpxTransport(
            base_url=base_url,
            verify=True,
            mock_transport=mock_transport,
        )

    async def get(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
        extra_headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            path,
            params=params,
            extra_headers=extra_headers,
            timeout=timeout,
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        request_id = str(uuid.uuid4())
        headers: dict[str, str] = {
            **self._auth.headers(),
            "X-Request-ID": request_id,
            "User-Agent": _USER_AGENT,
            **(extra_headers or {}),
        }

        with RequestTelemetry(
            method=method,
            url=f"{self._base_url}{path}",
            provider=self._provider_type,
        ) as tel:
            tel_ctx = tel  # keep reference to set status_code after request
            try:
                response = await self._transport.request(
                    method,
                    path,
                    headers=headers,
                    params=params,
                    json=json,
                    timeout=timeout or self._timeout,
                )
            except httpx.TimeoutException as exc:
                raise NetworkError("Request timed out", provider_type=self._provider_type) from exc
            except httpx.ConnectError as exc:
                raise NetworkError(
                    "Connection failed — DNS or connection refused",
                    provider_type=self._provider_type,
                ) from exc
            except httpx.RemoteProtocolError as exc:
                raise NetworkError(
                    f"Protocol error from provider: {exc}",
                    provider_type=self._provider_type,
                ) from exc
            except httpx.HTTPError as exc:
                raise NetworkError(
                    f"HTTP transport error: {exc}",
                    provider_type=self._provider_type,
                ) from exc

            tel_ctx.status_code = response.status_code

        if not response.is_success:
            raise map_http_error(response, provider_type=self._provider_type)

        try:
            return response.json()  # type: ignore[no-any-return]
        except Exception as exc:
            raise InternalProviderError(
                "Provider response is not valid JSON",
                provider_type=self._provider_type,
            ) from exc

    async def aclose(self) -> None:
        await self._transport.aclose()

    async def __aenter__(self) -> ProviderHttpClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()
