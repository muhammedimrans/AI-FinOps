"""HTTP transport abstraction — F-033.

Separating transport from client makes it trivial to inject httpx.MockTransport
in tests without monkey-patching.  Every adapter uses ProviderHttpClient (which
wraps HttpxTransport), so the entire HTTP layer is swap-friendly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import httpx


class HttpTransport(ABC):
    """Minimal async transport interface used by ProviderHttpClient."""

    @abstractmethod
    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> httpx.Response: ...

    @abstractmethod
    async def aclose(self) -> None: ...

    async def __aenter__(self) -> HttpTransport:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()


class HttpxTransport(HttpTransport):
    """Production transport backed by httpx.AsyncClient with connection pooling.

    Accepts an optional *mock_transport* (``httpx.AsyncBaseTransport``) so tests
    can inject ``httpx.MockTransport`` without touching real network code.
    """

    def __init__(
        self,
        *,
        base_url: str = "",
        default_headers: dict[str, str] | None = None,
        verify: bool = True,
        mock_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers=default_headers or {},
            verify=verify,
            transport=mock_transport,
        )

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> httpx.Response:
        return await self._client.request(
            method,
            url,
            headers=headers,
            params=params,
            json=json,
            timeout=timeout,
        )

    async def aclose(self) -> None:
        await self._client.aclose()
