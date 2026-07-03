"""
Azure OpenAI usage collector — honest stub.

Azure's cost/usage data lives in Azure Cost Management, gated behind Azure
AD (Entra ID) app registration and subscription-level RBAC — not reachable
with a simple API key the way OpenAI's Usage API is. That integration is
real work belonging to a future phase.

Implements the full BaseCollector interface so it participates in config,
health, and metrics like any other provider; collect() always returns an
empty list, and health() says exactly why.
"""

from __future__ import annotations

from typing import Any

from costorah_agent.collectors.base import BaseCollector
from costorah_agent.collectors.models import CollectorHealth, NormalizedUsageEvent

_UNSUPPORTED_DETAIL = (
    "Not implemented: Azure OpenAI usage requires Azure Cost Management API "
    "access via an Azure AD app registration, which this agent does not "
    "set up. See docs/TROUBLESHOOTING.md."
)


class AzureOpenAICollector(BaseCollector):
    name = "azure"

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
