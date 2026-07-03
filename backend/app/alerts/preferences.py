"""Per-user alert preferences — severity threshold, quiet hours, enabled
types. Applied at *read* time (the history/search API a user's client
calls), not at publish time: the underlying WebSocket connection is
organization-scoped, not per-user-filtered (see EP-19.1's connection
manager — every connection for an org receives every event for that
org), so preferences can't gate what's delivered over the live socket
without building a per-user routing layer this ticket doesn't ask for.
What they *do* gate is what `GET /v1/alerts` returns for a given caller,
and (if a later EP adds a digest job) what a daily digest includes.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, time

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import Alert, AlertPreference, AlertSeverity, severity_rank
from app.repositories.alert_repository import AlertPreferenceRepository


async def get_or_default(
    session: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID
) -> AlertPreference:
    """Returns the user's stored preference row, or an unsaved, in-memory
    default (empty allow-list = all types, INFO threshold = everything)
    without writing anything — a row is created lazily the first time the
    user actually changes a setting (see the PATCH endpoint)."""
    repo = AlertPreferenceRepository(session)
    existing = await repo.get_for_user(organization_id, user_id)
    if existing is not None:
        return existing
    return AlertPreference(
        organization_id=organization_id,
        user_id=user_id,
        enabled_alert_types=[],
        min_severity=AlertSeverity.INFO,
        quiet_hours_start_minute=None,
        quiet_hours_end_minute=None,
        timezone="UTC",
        daily_digest=False,
        immediate_notifications=True,
        max_notifications=None,
    )


def is_within_quiet_hours(preference: AlertPreference, *, now: datetime | None = None) -> bool:
    """True if `now` (in the preference's own timezone) falls inside the
    configured quiet-hours window. A window that wraps midnight (e.g.
    22:00-07:00) is handled by comparing against the wrap rather than
    assuming start < end."""
    if preference.quiet_hours_start_minute is None or preference.quiet_hours_end_minute is None:
        return False
    moment = now or datetime.now(UTC)
    minute_of_day = moment.hour * 60 + moment.minute
    start, end = preference.quiet_hours_start_minute, preference.quiet_hours_end_minute
    if start <= end:
        return start <= minute_of_day < end
    return minute_of_day >= start or minute_of_day < end  # wraps past midnight


def should_surface(preference: AlertPreference, alert: Alert) -> bool:
    """Whether `alert` passes this user's severity threshold and enabled-
    type allow-list. Does NOT consider quiet hours — quiet hours affect
    whether an *immediate* notification should be pushed, not whether the
    alert is visible in history at all (a user should always be able to
    see what happened while quiet hours were active)."""
    if severity_rank(alert.severity) < severity_rank(preference.min_severity):
        return False
    allowed_types = preference.enabled_alert_types
    if allowed_types and alert.alert_type.value not in allowed_types:
        return False
    return True


def minute_of_day(t: time) -> int:
    """Helper for the preferences API — converts a wall-clock `time` into
    the `quiet_hours_*_minute` integer representation stored on the row."""
    return t.hour * 60 + t.minute
