"""Real-time event model — EP-19.1.

Every event published through the event bus carries the same envelope
(`event_id`, `timestamp`, `organization_id`, `type`, `version`, `payload`,
`trace_id`, `correlation_id`), independent of which of the 12 event types
it is — one schema, one wire format, so WebSocket and SSE clients only
ever need to parse one shape.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class EventType(enum.StrEnum):
    """Every real-time event type named in the EP-19.1 ticket.

    Not every member here is currently *emitted* anywhere in the backend —
    see `docs/backend/REALTIME_EVENT_MODEL.md` for the honest accounting of
    which types this EP actually wires up (`USAGE_CREATED`) versus which
    are defined so the wire format/client SDKs are forward-compatible with
    a later EP that adds the triggering logic (budgets, provider health
    monitoring, notifications). Nothing here is a stub *handler* — this is
    just an enum of string values.
    """

    USAGE_CREATED = "usage.created"
    USAGE_UPDATED = "usage.updated"
    BUDGET_THRESHOLD_REACHED = "budget.threshold_reached"
    BUDGET_EXCEEDED = "budget.exceeded"
    PROVIDER_ERROR = "provider.error"
    PROVIDER_RECOVERY = "provider.recovery"
    API_KEY_CREATED = "api_key.created"
    API_KEY_DELETED = "api_key.deleted"
    SDK_CONNECTED = "sdk.connected"
    SDK_DISCONNECTED = "sdk.disconnected"
    ORGANIZATION_UPDATED = "organization.updated"
    NOTIFICATION_CREATED = "notification.created"


CURRENT_EVENT_VERSION = 1


class RealtimeEvent(BaseModel):
    """The envelope every event bus message is wrapped in.

    `trace_id`/`correlation_id` are carried through, never generated fresh
    here — callers pass whatever request-scoped identifiers already exist
    (e.g. structlog's contextvars-bound request ID) so a live event can be
    correlated with the log line / usage record that produced it.
    """

    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    organization_id: uuid.UUID
    type: EventType
    version: int = CURRENT_EVENT_VERSION
    payload: dict[str, Any] = Field(default_factory=dict)
    trace_id: str | None = None
    correlation_id: str | None = None

    def channel(self) -> str:
        return org_channel(self.organization_id)


def org_channel(organization_id: uuid.UUID) -> str:
    """The Redis Pub/Sub channel name for one organization's event stream."""
    return f"realtime:org:{organization_id}"


ORG_CHANNEL_PATTERN = "realtime:org:*"


def org_id_from_channel(channel: str) -> uuid.UUID | None:
    """Inverse of `org_channel` — parses the organization id back out of a
    channel name matched via `ORG_CHANNEL_PATTERN`. Returns None for any
    unrecognized channel rather than raising, since this is called on every
    message the pattern-subscribed dispatcher receives and a malformed
    channel must never crash the dispatch loop."""
    prefix = "realtime:org:"
    if not channel.startswith(prefix):
        return None
    try:
        return uuid.UUID(channel[len(prefix) :])
    except ValueError:
        return None
