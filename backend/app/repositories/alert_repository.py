"""
Repositories for the EP-19.3 alert engine — AlertRule, Alert,
AlertPreference, AlertSuppression. Pure data access; rule evaluation,
deduplication, and suppression logic live in app/alerts/.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Select, or_, select

from app.models.alert import (
    Alert,
    AlertPreference,
    AlertRule,
    AlertStatus,
    AlertSuppression,
    AlertType,
)
from app.repositories.base_repository import BaseRepository


class AlertRuleRepository(BaseRepository[AlertRule]):
    model = AlertRule

    async def list_enabled_for_type(
        self, organization_id: uuid.UUID, alert_type: AlertType
    ) -> list[AlertRule]:
        stmt = self._active_query().where(
            AlertRule.organization_id == organization_id,
            AlertRule.alert_type == alert_type,
            AlertRule.enabled.is_(True),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_org(self, organization_id: uuid.UUID) -> list[AlertRule]:
        stmt = (
            self._active_query()
            .where(AlertRule.organization_id == organization_id)
            .order_by(AlertRule.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class AlertRepository(BaseRepository[Alert]):
    model = Alert

    async def find_open_by_dedup_key(
        self, organization_id: uuid.UUID, dedup_key: str
    ) -> Alert | None:
        """The row a new occurrence should be folded into, if one is still
        open for this dedup key — see app/alerts/dedup.py."""
        stmt = self._active_query().where(
            Alert.organization_id == organization_id,
            Alert.dedup_key == dedup_key,
            Alert.status == AlertStatus.OPEN,
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    def _org_query(self, organization_id: uuid.UUID) -> Select[tuple[Alert]]:
        return self._active_query().where(Alert.organization_id == organization_id)

    async def list_for_org(
        self,
        organization_id: uuid.UUID,
        *,
        status: AlertStatus | None = None,
        severity: str | None = None,
        alert_type: AlertType | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        search: str | None = None,
        limit: int = 50,
    ) -> list[Alert]:
        """Filtered listing for the notification center's history/search/
        filter view (status, severity, alert_type, date range, free-text
        search over title/message). Unpaginated cursor-wise (capped at
        `limit`) — a future EP can add cursor pagination if history volume
        grows past what a single capped page comfortably serves."""
        stmt = self._org_query(organization_id)
        if status is not None:
            stmt = stmt.where(Alert.status == status)
        if severity is not None:
            stmt = stmt.where(Alert.severity == severity)
        if alert_type is not None:
            stmt = stmt.where(Alert.alert_type == alert_type)
        if since is not None:
            stmt = stmt.where(Alert.created_at >= since)
        if until is not None:
            stmt = stmt.where(Alert.created_at <= until)
        if search:
            like = f"%{search}%"
            stmt = stmt.where(or_(Alert.title.ilike(like), Alert.message.ilike(like)))
        stmt = stmt.order_by(Alert.created_at.desc()).limit(min(limit, 200))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_open_unacknowledged(self, organization_id: uuid.UUID) -> int:
        from sqlalchemy import func

        stmt = (
            select(func.count())
            .select_from(Alert)
            .where(
                Alert.organization_id == organization_id,
                Alert.deleted_at.is_(None),
                Alert.status == AlertStatus.OPEN,
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()


class AlertPreferenceRepository(BaseRepository[AlertPreference]):
    model = AlertPreference

    async def get_for_user(
        self, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> AlertPreference | None:
        stmt = self._active_query().where(
            AlertPreference.organization_id == organization_id,
            AlertPreference.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


class AlertSuppressionRepository(BaseRepository[AlertSuppression]):
    model = AlertSuppression

    async def list_active(
        self, organization_id: uuid.UUID, *, now: datetime
    ) -> list[AlertSuppression]:
        """Every suppression currently in effect for this org (any scope) —
        `app/alerts/suppression.py` narrows this down to what actually
        matches a specific firing alert's provider/type."""
        stmt = self._active_query().where(
            AlertSuppression.organization_id == organization_id,
            AlertSuppression.starts_at <= now,
            or_(AlertSuppression.ends_at.is_(None), AlertSuppression.ends_at >= now),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_org(self, organization_id: uuid.UUID) -> list[AlertSuppression]:
        stmt = (
            self._active_query()
            .where(AlertSuppression.organization_id == organization_id)
            .order_by(AlertSuppression.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
