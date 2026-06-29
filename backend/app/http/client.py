"""Shared provider HTTP client — F-033.

ProviderHttpClient wraps HttpTransport and adds:

* Per-request UUIDs injected as ``X-Request-ID`` (never logged with secret values)
* Structured request/response telemetry via RequestTelemetry
* Automatic HTTP error → ProviderError normalization (F-039)
* Retry loop driven by an injectable RetryPolicy (PH-02)
* Injectable mock_transport or shared_transport for hermetic unit testing (PH-01)

Security invariants
-------------------
* Auth headers are built by HttpAuth strategies — the credential string is
  passed in at construction time but is never written to any log line.
* ``User-Agent`` identifies the platform version without leaking credentials.

Connection lifecycle (PH-01)
----------------------------
``ProviderHttpClient`` may operate in two modes:

owned transport
    Constructed without a ``transport`` argument. ``HttpxTransport`` is created
    internally and closed when ``aclose()`` is called.  Used by standalone
    clients and tests that need total isolation.

shared transport
    Constructed with ``transport=<HttpxTransport instance>``.  The client does
    NOT close the transport on ``aclose()``; the owner (adapter or pool) is
    responsible for lifecycle.  This is the mode used by provider adapters so
    that the underlying ``httpx.AsyncClient`` connection pool persists across
    multiple method calls.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import httpx

from app.http.auth import HttpAuth
from app.http.telemetry import RequestTelemetry
from app.http.transport import HttpTransport, HttpxTransport
from app.providers.errors import (
    AuthenticationError,
    InternalProviderError,
    InvalidRequestError,
    NetworkError,
    ProviderError,
    RateLimitError,
)
from app.providers.retry import RetryPolicy

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

    **Owned transport** (default) — pass *mock_transport* for test isolation::

        transport = httpx.MockTransport(handler=my_handler)
        client = ProviderHttpClient(
            base_url="https://api.openai.com",
            auth=BearerTokenAuth(key),
            provider_type="openai",
            mock_transport=transport,
        )

    **Shared transport** (PH-01, production) — pass a pre-built *transport* so
    the connection pool persists across calls::

        http_transport = HttpxTransport(base_url="https://api.openai.com", verify=True)
        client = ProviderHttpClient(
            base_url="https://api.openai.com",
            auth=BearerTokenAuth(key),
            provider_type="openai",
            transport=http_transport,  # not owned; caller closes it
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
        transport: HttpTransport | None = None,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self._base_url = base_url
        self._auth = auth
        self._provider_type = provider_type
        self._timeout = timeout

        if transport is not None:
            self._transport = transport
            self._owns_transport = False
        else:
            self._transport = HttpxTransport(
                base_url=base_url,
                verify=True,
                mock_transport=mock_transport,
            )
            self._owns_transport = True

        # Default to ExponentialRetryPolicy; allow override (e.g. zero-delay in tests).
        if retry_policy is not None:
            self._retry_policy: RetryPolicy = retry_policy
        else:
            from app.http.retry import ExponentialRetryPolicy

            self._retry_policy = ExponentialRetryPolicy()

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

    async def post(
        self,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
        extra_headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """POST convenience method — available for EP-08 usage-collection endpoints."""
        return await self._request(
            "POST",
            path,
            json=json,
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
        attempt = 0
        while True:
            attempt += 1
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
                    err: ProviderError = NetworkError(
                        "Request timed out", provider_type=self._provider_type
                    )
                    tel.error = type(exc).__name__
                    if self._retry_policy.should_retry(attempt, err):
                        await asyncio.sleep(self._retry_policy.get_delay(attempt))
                        continue
                    raise err from exc
                except httpx.ConnectError as exc:
                    err = NetworkError(
                        "Connection failed — DNS or connection refused",
                        provider_type=self._provider_type,
                    )
                    tel.error = type(exc).__name__
                    if self._retry_policy.should_retry(attempt, err):
                        await asyncio.sleep(self._retry_policy.get_delay(attempt))
                        continue
                    raise err from exc
                except httpx.RemoteProtocolError as exc:
                    err = NetworkError(
                        f"Protocol error from provider: {exc}",
                        provider_type=self._provider_type,
                    )
                    tel.error = type(exc).__name__
                    if self._retry_policy.should_retry(attempt, err):
                        await asyncio.sleep(self._retry_policy.get_delay(attempt))
                        continue
                    raise err from exc
                except httpx.HTTPError as exc:
                    err = NetworkError(
                        f"HTTP transport error: {exc}",
                        provider_type=self._provider_type,
                    )
                    tel.error = type(exc).__name__
                    if self._retry_policy.should_retry(attempt, err):
                        await asyncio.sleep(self._retry_policy.get_delay(attempt))
                        continue
                    raise err from exc

                tel.status_code = response.status_code

            if not response.is_success:
                provider_err = map_http_error(response, provider_type=self._provider_type)
                if self._retry_policy.should_retry(attempt, provider_err):
                    # Honour Retry-After from 429 responses when available.
                    if (
                        isinstance(provider_err, RateLimitError)
                        and provider_err.retry_after_seconds is not None
                    ):
                        delay = min(
                            provider_err.retry_after_seconds,
                            self._retry_policy.get_config().max_delay_seconds,
                        )
                    else:
                        delay = self._retry_policy.get_delay(attempt)
                    await asyncio.sleep(delay)
                    continue
                raise provider_err

            try:
                return response.json()  # type: ignore[no-any-return]
            except Exception as exc:
                raise InternalProviderError(
                    "Provider response is not valid JSON",
                    provider_type=self._provider_type,
                ) from exc

    async def aclose(self) -> None:
        """Close the transport if this client owns it; no-op for shared transports."""
        if self._owns_transport:
            await self._transport.aclose()

    async def __aenter__(self) -> ProviderHttpClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()
