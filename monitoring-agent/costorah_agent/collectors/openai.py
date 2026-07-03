"""
OpenAI usage collector — real HTTP calls to OpenAI's Usage API.

Requires an OpenAI **Admin** API key (regular project keys cannot read
org-wide usage) — https://platform.openai.com/docs/api-reference/usage.
Read from config `providers_config.openai.api_key` or the standard
`OPENAI_API_KEY` environment variable.

Known limitation (documented, not hidden): the Usage API reports tokens
and request counts per bucket, not cost. A production-accurate cost figure
requires the separate Costs API (`GET /v1/organization/costs`), which is
not implemented in this phase — `cost` is reported as 0.0 until that's
added. This is exactly the kind of gap this project's engineering practice
flags explicitly rather than fabricating a number.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

from costorah_agent.collectors._util import deterministic_request_id, env_or_config
from costorah_agent.collectors.base import BaseCollector, CollectorError
from costorah_agent.collectors.models import CollectorHealth, NormalizedUsageEvent

log = structlog.get_logger(__name__)

_USAGE_URL = "https://api.openai.com/v1/organization/usage/completions"


class OpenAICollector(BaseCollector):
    name = "openai"

    def __init__(
        self, config: dict[str, Any], *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        super().__init__(config)
        self._api_key = env_or_config(config, "api_key", "OPENAI_API_KEY")
        self._client = httpx.AsyncClient(timeout=10.0, transport=transport)
        self._last_start_time = int(time.time()) - 300  # look back 5 min on first poll
        self._last_collected_at: datetime | None = None
        self._last_error: str | None = None

    async def collect(self) -> list[NormalizedUsageEvent]:
        if not self._api_key:
            self._last_error = "OPENAI_API_KEY not configured"
            return []

        now = int(time.time())
        try:
            resp = await self._client.get(
                _USAGE_URL,
                headers={"Authorization": f"Bearer {self._api_key}"},
                params={"start_time": self._last_start_time, "bucket_width": "1m"},
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            self._last_error = str(exc)
            log.warning("openai_usage_fetch_failed", error=str(exc))
            return []

        self._last_start_time = now
        self._last_collected_at = datetime.now(UTC)
        self._last_error = None

        events: list[NormalizedUsageEvent] = []
        try:
            body = resp.json()
        except ValueError as exc:
            raise CollectorError(f"OpenAI usage response was not valid JSON: {exc}") from exc

        for bucket in body.get("data", []):
            for result in bucket.get("results", []):
                events.append(self.normalize({"bucket": bucket, "result": result}))

        self._record_collected(len(events))
        return events

    def normalize(self, raw: Any) -> NormalizedUsageEvent:
        bucket = raw["bucket"]
        result = raw["result"]
        start_time = bucket.get("start_time", 0)
        end_time = bucket.get("end_time", start_time)
        model = result.get("model", "unknown")
        input_tokens = int(result.get("input_tokens", 0))
        output_tokens = int(result.get("output_tokens", 0))
        request_count = int(result.get("num_model_requests", 1))

        return NormalizedUsageEvent(
            provider="openai",
            model=model,
            request_id=deterministic_request_id("openai", str(start_time), str(end_time), model),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            cost=0.0,  # see module docstring — Costs API not wired up yet
            status="success",
            timestamp=datetime.fromtimestamp(end_time, tz=UTC),
            metadata={"request_count": request_count, "bucket_start": start_time},
        )

    async def health(self) -> CollectorHealth:
        return CollectorHealth(
            name=self.name,
            enabled=True,
            healthy=self._api_key is not None and self._last_error is None,
            detail=(
                "OPENAI_API_KEY not configured" if not self._api_key else (self._last_error or "ok")
            ),
            last_collected_at=self._last_collected_at,
            events_collected_total=self._events_collected_total,
        )

    async def shutdown(self) -> None:
        await self._client.aclose()
