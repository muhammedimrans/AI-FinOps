"""
Ollama usage collector — real connectivity check, honest about usage data.

Ollama is a local model runner with no billing and no usage/cost-tracking
API of any kind — there is nothing to "collect" in the sense every other
collector means it. collect() always returns an empty list; fabricating a
zero-cost event per request would misrepresent real usage as a monitored
data point when it's actually just an absence of data.

What this collector *does* do for real: health() performs a live
connectivity check against Ollama's local API (`GET /api/tags`), which is
genuinely useful for confirming the agent can reach the local Ollama
daemon, independent of the fact that there's no usage endpoint to poll.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from costorah_agent.collectors.base import BaseCollector
from costorah_agent.collectors.models import CollectorHealth, NormalizedUsageEvent

_DEFAULT_BASE_URL = "http://localhost:11434"
_NO_USAGE_API_DETAIL = (
    "Ollama has no usage/cost-tracking API — local models are free and "
    "unmetered. This collector only verifies connectivity."
)


class OllamaCollector(BaseCollector):
    name = "ollama"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._base_url = str(config.get("base_url", _DEFAULT_BASE_URL)).rstrip("/")
        self._client = httpx.AsyncClient(timeout=5.0)
        self._last_reachable: bool | None = None
        self._last_checked_at: datetime | None = None

    async def collect(self) -> list[NormalizedUsageEvent]:
        # No usage API exists — see module docstring. Still worth polling
        # connectivity so health() stays current.
        await self._check_connectivity()
        return []

    def normalize(self, raw: Any) -> NormalizedUsageEvent:
        raise NotImplementedError(_NO_USAGE_API_DETAIL)

    async def _check_connectivity(self) -> None:
        try:
            resp = await self._client.get(f"{self._base_url}/api/tags")
            self._last_reachable = resp.status_code == 200
        except httpx.HTTPError:
            self._last_reachable = False
        self._last_checked_at = datetime.now(UTC)

    async def health(self) -> CollectorHealth:
        if self._last_checked_at is None:
            await self._check_connectivity()
        detail = _NO_USAGE_API_DETAIL
        if not self._last_reachable:
            detail = f"Ollama unreachable at {self._base_url}. {_NO_USAGE_API_DETAIL}"
        return CollectorHealth(
            name=self.name,
            enabled=True,
            healthy=bool(self._last_reachable),
            detail=detail,
            last_collected_at=self._last_checked_at,
            events_collected_total=self._events_collected_total,
        )

    async def shutdown(self) -> None:
        await self._client.aclose()
