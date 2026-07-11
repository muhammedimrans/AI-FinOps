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
import structlog

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

log = structlog.get_logger(__name__)

_USER_AGENT = "aifinops/0.1.0 (provider-integration)"

# EP-26.0.3.4 — never log an actual credential value even though provider
# response headers essentially never echo one back; this is defense in
# depth, not a signal that any provider is known to do so.
_SENSITIVE_HEADER_NAMES = frozenset(
    {"authorization", "api-key", "x-api-key", "x-goog-api-key", "set-cookie", "cookie"}
)

_ERROR_BODY_LOG_LIMIT = 4000


def _parse_retry_after(response: httpx.Response) -> float | None:
    raw = response.headers.get("Retry-After") or response.headers.get("retry-after")
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _redacted_response_headers(response: httpx.Response) -> dict[str, str]:
    return {
        name: ("<redacted>" if name.lower() in _SENSITIVE_HEADER_NAMES else value)
        for name, value in response.headers.items()
    }


def _parse_error_body(response: httpx.Response) -> tuple[dict[str, Any] | None, str]:
    """Best-effort parse of an error response body.

    Returns ``(parsed_json_or_None, raw_text_truncated)`` — the raw text is
    always captured (truncated to a sane log size), even when the body
    isn't valid JSON, so an HTML error page or a plain-text message from an
    upstream proxy is never silently discarded either.
    """
    try:
        raw_text = response.text
    except Exception:
        raw_text = ""
    truncated = raw_text[:_ERROR_BODY_LOG_LIMIT]
    try:
        parsed = response.json()
    except Exception:
        return None, truncated
    return (parsed if isinstance(parsed, dict) else None), truncated


def _extract_provider_error_detail(
    body: dict[str, Any] | None,
) -> tuple[str | None, str | None, str | None]:
    """Best-effort extraction of ``(message, code, status)`` from a
    provider's own JSON error body — never assumed, always attempted from
    whatever shape is actually present.

    Handles two conventions in the wild:

    * Google's Gemini API: ``{"error": {"code": <int>, "message": <str>,
      "status": <str>}}`` — e.g. ``{"error": {"code": 400, "message":
      "Unknown name \\"max_tokens\\": Cannot find field.", "status":
      "INVALID_ARGUMENT"}}``.
    * The OpenAI-compatible convention most other providers in this
      catalog use: ``{"error": {"message": <str>, "type": <str>, "code":
      <str|int|None>}}``.

    Both shapes nest under one top-level ``"error"`` key, so one extractor
    covers both — ``status`` falls back to OpenAI's ``type`` field when
    Google's ``status`` key isn't present. Returns ``(None, None, None)``
    when the body doesn't match either shape (e.g. no body, or a body
    that isn't a JSON object at all) rather than raising.
    """
    if not body:
        return None, None, None
    err = body.get("error")
    if not isinstance(err, dict):
        return None, None, None
    message = err.get("message")
    code = err.get("code")
    status = err.get("status") or err.get("type")
    return (
        str(message) if message is not None else None,
        str(code) if code is not None else None,
        str(status) if status is not None else None,
    )


def map_http_error(response: httpx.Response, *, provider_type: str) -> ProviderError:
    """Convert an unsuccessful HTTP response to the appropriate ProviderError (F-039).

    EP-26.0.3.4: never swallows the response. Every branch below attempts to
    parse the provider's own error body (Google's ``{"error": {"code",
    "message", "status"}}`` shape, or the OpenAI-compatible ``{"error":
    {"message", "type"}}`` shape) and folds the real ``message``/``code``/
    ``status`` into the raised exception's own message — a caller-facing
    "Unexpected HTTP 400" with the actual reason discarded is exactly the
    defect this rewrite closes.
    """
    body, raw_text = _parse_error_body(response)
    message, code, status = _extract_provider_error_detail(body)
    detail = message or (raw_text if raw_text.strip() else None)

    match response.status_code:
        case 400:
            text = detail or "Invalid request"
            if status or code:
                text = f"{text} (status={status or 'unknown'}, code={code or response.status_code})"
            return InvalidRequestError(text, provider_type=provider_type)
        case 401:
            text = "Invalid API key or unauthorized"
            if detail:
                text = f"{text}: {detail}"
            return AuthenticationError(text, provider_type=provider_type)
        case 403:
            text = "Access forbidden — check API key permissions or org settings"
            if detail:
                text = f"{text}: {detail}"
            return AuthenticationError(text, provider_type=provider_type)
        case 404:
            text = detail or f"Endpoint not found: {response.url}"
            return InvalidRequestError(text, provider_type=provider_type)
        case 408 | 504:
            return NetworkError("Request timed out", provider_type=provider_type)
        case 409 | 422:
            text = detail or "Invalid request"
            if status or code:
                text = f"{text} (status={status or 'unknown'}, code={code or response.status_code})"
            return InvalidRequestError(text, provider_type=provider_type)
        case 429:
            text = "Rate limit exceeded"
            if detail:
                text = f"{text}: {detail}"
            return RateLimitError(
                text,
                provider_type=provider_type,
                retry_after_seconds=_parse_retry_after(response),
            )
        case 500 | 502 | 503:
            text = f"Provider server error ({response.status_code})"
            if detail:
                text = f"{text}: {detail}"
            return InternalProviderError(text, provider_type=provider_type)
        case _:
            text = f"Unexpected HTTP {response.status_code}"
            if detail:
                text = f"{text}: {detail}"
            return ProviderError(text, provider_type=provider_type)


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
                # EP-26.0.3.4 — instrument every non-2xx provider response
                # before it's mapped/discarded: status, response headers
                # (secret-bearing header names redacted defensively — see
                # _SENSITIVE_HEADER_NAMES), the raw body, and whatever
                # provider-reported error code/message/status
                # map_http_error() was able to extract from it. This is the
                # one place in the whole HTTP layer every adapter's error
                # path funnels through, so instrumenting it here covers
                # every provider (Google's INVALID_ARGUMENT 400s included),
                # not just one adapter.
                error_body, error_raw_text = _parse_error_body(response)
                error_message, error_code, error_status = _extract_provider_error_detail(error_body)
                log.warning(
                    "provider_http_error_response",
                    provider=self._provider_type,
                    method=method,
                    path=path,
                    request_id=request_id,
                    status_code=response.status_code,
                    response_headers=_redacted_response_headers(response),
                    response_body=error_raw_text,
                    provider_error_code=error_code,
                    provider_error_message=error_message,
                    provider_error_status=error_status,
                )
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
