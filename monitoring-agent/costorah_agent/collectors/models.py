"""
Internal normalized usage event — the common currency every collector
produces, regardless of provider.

Field names and semantics are deliberately identical to EP-16's
`IngestUsageRequest` (backend/app/schemas/usage_ingestion.py) so the
transport layer can serialize this directly as the ingestion request body
with no translation step. The agent does not import backend code (it is a
separate, independently distributable project) — this is a parallel,
intentionally-matching definition, not a shared import.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

UsageStatus = Literal["success", "error", "timeout", "cancelled"]


@dataclass(slots=True)
class NormalizedUsageEvent:
    """One usage record, normalized to the EP-16 ingestion schema."""

    provider: str
    model: str
    request_id: str
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int | None = None
    total_tokens: int | None = None
    cost: float = 0.0
    currency: str = "USD"
    latency_ms: int | None = None
    status: UsageStatus = "success"
    region: str | None = None
    project_id: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_ingestion_payload(self) -> dict[str, Any]:
        """Return the exact JSON body POST /v1/ingest/usage expects."""
        payload: dict[str, Any] = {
            "provider": self.provider,
            "model": self.model,
            "request_id": self.request_id,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost": self.cost,
            "currency": self.currency,
            "status": self.status,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }
        if self.cached_tokens is not None:
            payload["cached_tokens"] = self.cached_tokens
        if self.total_tokens is not None:
            payload["total_tokens"] = self.total_tokens
        if self.latency_ms is not None:
            payload["latency_ms"] = self.latency_ms
        if self.region is not None:
            payload["region"] = self.region
        if self.project_id is not None:
            payload["project_id"] = self.project_id
        return payload


@dataclass(slots=True)
class CollectorHealth:
    """Health/status snapshot for one collector, surfaced via the agent's
    own /health endpoint and `costorah-agent health`."""

    name: str
    enabled: bool
    healthy: bool
    detail: str
    last_collected_at: datetime | None = None
    events_collected_total: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "enabled": self.enabled,
            "healthy": self.healthy,
            "detail": self.detail,
            "last_collected_at": (
                self.last_collected_at.isoformat() if self.last_collected_at else None
            ),
            "events_collected_total": self.events_collected_total,
        }
