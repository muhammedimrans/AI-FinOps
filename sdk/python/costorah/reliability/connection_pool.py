"""
ConnectionPool — a single shared `httpx.AsyncClient`, reused across every
delivery attempt instead of opening a new connection per request. httpx
already pools/keeps-alive connections per host internally; this wrapper's
job is just to make sure the whole reliability layer shares exactly one
such client (and its pool) rather than constructing one per request.
"""

from __future__ import annotations

import httpx

from costorah.config import Config
from costorah.version import __version__


class ConnectionPool:
    def __init__(
        self,
        config: Config,
        *,
        max_connections: int = 20,
        max_keepalive_connections: int = 10,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._config = config
        self.requests_sent = 0
        self._client = httpx.AsyncClient(
            base_url=config.endpoint,
            timeout=config.timeout,
            verify=config.verify_tls,
            transport=transport,
            limits=httpx.Limits(
                max_connections=max_connections,
                max_keepalive_connections=max_keepalive_connections,
            ),
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "User-Agent": f"costorah-python/{__version__}",
            },
        )

    async def post(self, path: str, *, content: bytes, headers: dict[str, str]) -> httpx.Response:
        self.requests_sent += 1
        return await self._client.post(path, content=content, headers=headers)

    async def aclose(self) -> None:
        await self._client.aclose()
