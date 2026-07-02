"""
Anthropic usage collector — real HTTP call to Anthropic's usage report API.

Requires an Anthropic **Admin** API key (`ANTHROPIC_ADMIN_KEY`), distinct
from a regular API key — Anthropic's usage/cost reporting is only exposed
to org admins. Mirrors the COSTORAH backend's own EP-08 Anthropic adapter
precedent: usage reporting is treated as an optional capability that fails
silently (health() reports the degraded state; collect() returns an empty
list) rather than raising and interrupting the collection loop for every
other provider.
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

_USAGE_URL = "https://api.anthropic.com/v1/organizations/usage_report/messages"
_ANTHROPIC_VERSION = "2023-06-01"


class AnthropicCollector(BaseCollector):
    name = "anthropic"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._admin_key = env_or_config(config, "admin_api_key", "ANTHROPIC_ADMIN_KEY")
        self._client = httpx.AsyncClient(timeout=10.0)
        self._last_collected_at: datetime | None = None
        self._last_error: str | None = None

    async def collect(self) -> list[NormalizedUsageEvent]:
        if not self._admin_key:
            self._last_error = "ANTHROPIC_ADMIN_KEY not configured"
            return []

        try:
            resp = await self._client.get(
                _USAGE_URL,
                headers={
                    "x-api-key": self._admin_key,
                    "anthropic-version": _ANTHROPIC_VERSION,
                },
                params={"bucket_width": "1m"},
            )
            resp.raise_for_status()
            body = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            # Optional-capability failure: log and move on, exactly like
            # the backend's own Anthropic get_usage() adapter.
            self._last_error = str(exc)
            log.warning("anthropic_usage_fetch_failed", error=str(exc))
            return []

        self._last_collected_at = datetime.now(UTC)
        self._last_error = None

        events: list[NormalizedUsageEvent] = []
        for bucket in body.get("data", []):
            for result in bucket.get("results", []):
                events.append(self.normalize({"bucket": bucket, "result": result}))

        self._record_collected(len(events))
        return events

    def normalize(self, raw: Any) -> NormalizedUsageEvent:
        bucket = raw["bucket"]
        result = raw["result"]
        end_time = bucket.get("end_time", 0)
        model = result.get("model", "unknown")
        input_tokens = int(result.get("uncached_input_tokens", 0))
        output_tokens = int(result.get("output_tokens", 0))
        cached_tokens = int(result.get("cache_read_input_tokens", 0)) or None

        return NormalizedUsageEvent(
            provider="anthropic",
            model=model,
            request_id=deterministic_request_id(
                "anthropic", str(bucket.get("start_time", 0)), str(end_time), model
            ),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            total_tokens=input_tokens + output_tokens,
            cost=0.0,  # usage report has no cost field; cost API is separate
            status="success",
            timestamp=datetime.fromtimestamp(end_time, tz=UTC) if end_time else datetime.now(UTC),
            metadata={},
        )

    async def health(self) -> CollectorHealth:
        return CollectorHealth(
            name=self.name,
            enabled=True,
            healthy=self._admin_key is not None and self._last_error is None,
            detail=(
                "ANTHROPIC_ADMIN_KEY not configured"
                if not self._admin_key
                else (self._last_error or "ok")
            ),
            last_collected_at=self._last_collected_at,
            events_collected_total=self._events_collected_total,
        )

    async def shutdown(self) -> None:
        await self._client.aclose()
