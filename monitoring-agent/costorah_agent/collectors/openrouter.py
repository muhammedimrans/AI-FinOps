"""
OpenRouter usage collector — real HTTP call to OpenRouter's key-info API.

Known limitation (documented, not hidden): OpenRouter's public API exposes
account-level aggregate spend via `GET /api/v1/auth/key`
(https://openrouter.ai/docs/api-reference/get-current-api-key). Per-request
usage requires passing back the `generation_id` returned by *your own*
completion calls (`GET /api/v1/generation?id=...`), which this collector
doesn't have — it only sees the account from outside. So each poll emits
at most one synthetic event representing the *delta* in total spend since
the last poll, not one event per request. This is real data (not
fabricated), just coarser granularity than a per-request collector.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

from costorah_agent.collectors._util import deterministic_request_id, env_or_config
from costorah_agent.collectors.base import BaseCollector
from costorah_agent.collectors.models import CollectorHealth, NormalizedUsageEvent

log = structlog.get_logger(__name__)

_KEY_INFO_URL = "https://openrouter.ai/api/v1/auth/key"


class OpenRouterCollector(BaseCollector):
    name = "openrouter"

    def __init__(
        self, config: dict[str, Any], *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        super().__init__(config)
        self._api_key = env_or_config(config, "api_key", "OPENROUTER_API_KEY")
        self._client = httpx.AsyncClient(timeout=10.0, transport=transport)
        self._last_usage: float | None = None
        self._last_collected_at: datetime | None = None
        self._last_error: str | None = None

    async def collect(self) -> list[NormalizedUsageEvent]:
        if not self._api_key:
            self._last_error = "OPENROUTER_API_KEY not configured"
            return []

        try:
            resp = await self._client.get(
                _KEY_INFO_URL, headers={"Authorization": f"Bearer {self._api_key}"}
            )
            resp.raise_for_status()
            body = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            self._last_error = str(exc)
            log.warning("openrouter_key_info_failed", error=str(exc))
            return []

        self._last_collected_at = datetime.now(UTC)
        self._last_error = None

        data = body.get("data", {})
        total_usage = float(data.get("usage", 0.0))

        if self._last_usage is None:
            # First poll establishes the baseline; nothing to report yet
            # (we don't know how much of the lifetime total predates this
            # agent starting, so reporting it now would double-count
            # everything the customer already saw before installing the
            # agent).
            self._last_usage = total_usage
            return []

        delta = total_usage - self._last_usage
        self._last_usage = total_usage
        if delta <= 0:
            return []

        event = self.normalize({"delta_cost": delta, "label": data.get("label", "unknown")})
        self._record_collected(1)
        return [event]

    def normalize(self, raw: Any) -> NormalizedUsageEvent:
        now = datetime.now(UTC)
        return NormalizedUsageEvent(
            provider="openrouter",
            model="aggregate",  # account-level; no single model applies
            request_id=deterministic_request_id("openrouter", now.isoformat()),
            cost=round(float(raw["delta_cost"]), 8),
            status="success",
            timestamp=now,
            metadata={"granularity": "account_aggregate_delta", "label": raw.get("label")},
        )

    async def health(self) -> CollectorHealth:
        return CollectorHealth(
            name=self.name,
            enabled=True,
            healthy=self._api_key is not None and self._last_error is None,
            detail=(
                "OPENROUTER_API_KEY not configured"
                if not self._api_key
                else (self._last_error or "ok")
            ),
            last_collected_at=self._last_collected_at,
            events_collected_total=self._events_collected_total,
        )

    async def shutdown(self) -> None:
        await self._client.aclose()
