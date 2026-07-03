"""
Google (Vertex AI / Gemini) usage collector — honest stub.

Google Cloud does not expose per-request AI usage/cost via a simple API-key
call the way OpenAI/OpenRouter do. Getting real usage data requires GCP
Billing Export to BigQuery (a project-level, IAM-gated setup step outside
this agent's control) and then querying that export. That integration is
real work belonging to a future phase, not something to fake here.

This collector implements the full BaseCollector interface so it can be
enabled in config and reported on by the health/metrics endpoints like any
other provider, but collect() always returns an empty list, and health()
says exactly why — never a silently-fabricated zero-cost event.
"""

from __future__ import annotations

from typing import Any

from costorah_agent.collectors.base import BaseCollector
from costorah_agent.collectors.models import CollectorHealth, NormalizedUsageEvent

_UNSUPPORTED_DETAIL = (
    "Not implemented: Google Cloud AI usage requires BigQuery billing "
    "export configuration, which this agent does not set up or query. "
    "See docs/TROUBLESHOOTING.md."
)


class GoogleCollector(BaseCollector):
    name = "google"

    async def collect(self) -> list[NormalizedUsageEvent]:
        return []

    def normalize(self, raw: Any) -> NormalizedUsageEvent:
        raise NotImplementedError(_UNSUPPORTED_DETAIL)

    async def health(self) -> CollectorHealth:
        return CollectorHealth(
            name=self.name,
            enabled=True,
            healthy=False,
            detail=_UNSUPPORTED_DETAIL,
            events_collected_total=self._events_collected_total,
        )
