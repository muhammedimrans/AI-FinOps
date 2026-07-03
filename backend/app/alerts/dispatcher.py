"""AlertService — the single entry point every trigger call site uses to
fire an alert. Persists (with dedup + suppression applied) and publishes
to the EventBus for live delivery, reusing EP-19.1's infrastructure
end to end rather than adding a parallel one.

Call sites (see docs/realtime/ALERT_ARCHITECTURE.md for the full list):
  app/api/v1/ingest.py     — budget_threshold / budget_exceeded
  app/api/v1/providers.py  — provider_error / provider_recovery
  app/services/organization_api_key_service.py — api_key_created / api_key_revoked
  app/api/v1/organizations.py — org_member_added / org_member_removed
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts import metrics as alert_metrics
from app.alerts.dedup import build_dedup_key
from app.alerts.suppression import is_suppressed
from app.models.alert import Alert, AlertSeverity, AlertStatus, AlertType
from app.realtime.event_bus import EventBus
from app.realtime.events import EventType, RealtimeEvent
from app.repositories.alert_repository import AlertRepository

# AlertType -> the existing EventType this rides on, reusing EP-19.1's
# already-defined (and, for these members, now truly emitted) event
# types instead of inventing new ones. Anything not listed here falls
# back to the generic NOTIFICATION_CREATED.
_EVENT_TYPE_MAP: dict[AlertType, EventType] = {
    AlertType.BUDGET_THRESHOLD: EventType.BUDGET_THRESHOLD_REACHED,
    AlertType.BUDGET_EXCEEDED: EventType.BUDGET_EXCEEDED,
    AlertType.PROVIDER_ERROR: EventType.PROVIDER_ERROR,
    AlertType.PROVIDER_RECOVERY: EventType.PROVIDER_RECOVERY,
    AlertType.API_KEY_CREATED: EventType.API_KEY_CREATED,
    AlertType.API_KEY_REVOKED: EventType.API_KEY_DELETED,
    AlertType.ORG_MEMBER_ADDED: EventType.ORGANIZATION_UPDATED,
    AlertType.ORG_MEMBER_REMOVED: EventType.ORGANIZATION_UPDATED,
}


class AlertService:
    def __init__(self, session: AsyncSession, event_bus: EventBus) -> None:
        self._session = session
        self._alerts = AlertRepository(session)
        self._event_bus = event_bus

    async def fire(
        self,
        *,
        organization_id: uuid.UUID,
        alert_type: AlertType,
        severity: AlertSeverity,
        title: str,
        message: str,
        source: str,
        scope: str,
        provider: str | None = None,
        rule_id: uuid.UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Alert | None:
        """Fires one alert occurrence. Returns the (possibly deduplicated)
        `Alert` row, or `None` if it was suppressed. Never raises on a
        Redis/EventBus failure — persistence always succeeds independent
        of whether live delivery does (matching `EventBus.publish()`'s own
        never-raise contract)."""
        now = datetime.now(UTC)

        suppression = await is_suppressed(
            self._session,
            organization_id=organization_id,
            alert_type=alert_type,
            provider=provider,
            now=now,
        )
        if suppression is not None:
            alert_metrics.alerts_suppressed_total.labels(alert_type=alert_type.value).inc()
            return None

        dedup_key = build_dedup_key(alert_type, scope)
        existing = await self._alerts.find_open_by_dedup_key(organization_id, dedup_key)

        if existing is not None:
            existing.occurrence_count += 1
            existing.last_occurred_at = now
            existing.message = message
            if metadata:
                existing.alert_metadata = {**existing.alert_metadata, **metadata}
            await self._session.flush()
            alert_metrics.alerts_deduplicated_total.labels(alert_type=alert_type.value).inc()
            alert = existing
        else:
            alert = await self._alerts.create(
                Alert(
                    organization_id=organization_id,
                    rule_id=rule_id,
                    alert_type=alert_type,
                    severity=severity,
                    status=AlertStatus.OPEN,
                    title=title,
                    message=message,
                    source=source,
                    dedup_key=dedup_key,
                    occurrence_count=1,
                    alert_metadata=metadata or {},
                    first_occurred_at=now,
                    last_occurred_at=now,
                )
            )
            alert_metrics.alerts_created_total.labels(
                alert_type=alert_type.value, severity=severity.value
            ).inc()

        await self._publish(alert)
        return alert

    async def _publish(self, alert: Alert) -> None:
        event_type = _EVENT_TYPE_MAP.get(alert.alert_type, EventType.NOTIFICATION_CREATED)
        with alert_metrics.notification_latency_seconds.time():
            await self._event_bus.publish(
                RealtimeEvent(
                    organization_id=alert.organization_id,
                    type=event_type,
                    payload={
                        "alert_id": str(alert.id),
                        "alert_type": alert.alert_type.value,
                        "severity": alert.severity.value,
                        "status": alert.status.value,
                        "title": alert.title,
                        "message": alert.message,
                        "occurrence_count": alert.occurrence_count,
                        **alert.alert_metadata,
                    },
                )
            )
        alert_metrics.alerts_delivered_total.labels(alert_type=alert.alert_type.value).inc()
