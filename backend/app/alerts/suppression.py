"""Suppression — should a firing alert be silently skipped right now?

Three scopes, checked independently (any match suppresses):
  ORGANIZATION — every alert type is suppressed org-wide (e.g. a planned
                 maintenance window).
  PROVIDER     — suppressed only when the firing alert's metadata names a
                 provider matching the suppression's `target`.
  ALERT_TYPE   — suppressed only when the firing alert's type matches
                 `target`.

A suppressed alert is still counted (see `app.alerts.metrics`'s
`alerts_suppressed_total`) — suppression means "don't create/deliver a
notification", not "pretend this never happened".
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import AlertSuppression, AlertType, SuppressionScope
from app.repositories.alert_repository import AlertSuppressionRepository


async def is_suppressed(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    alert_type: AlertType,
    provider: str | None,
    now: datetime | None = None,
) -> AlertSuppression | None:
    """Returns the matching suppression, or None if nothing applies."""
    repo = AlertSuppressionRepository(session)
    active = await repo.list_active(organization_id, now=now or datetime.now(UTC))
    for suppression in active:
        if suppression.scope == SuppressionScope.ORGANIZATION:
            return suppression
        if (
            suppression.scope == SuppressionScope.ALERT_TYPE
            and suppression.target == alert_type.value
        ):
            return suppression
        if (
            suppression.scope == SuppressionScope.PROVIDER
            and provider is not None
            and suppression.target == provider
        ):
            return suppression
    return None
