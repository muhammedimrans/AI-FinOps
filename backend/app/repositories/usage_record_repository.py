"""
UsageRecordRepository — data access for UsageRecord entities (EP-16).

Only data-access logic belongs here. Validation, normalization, dedup
orchestration, and dual-writing into the EP-08/EP-09 tables belong in
UsageIngestionService.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.usage_record import UsageRecord
from app.repositories.base_repository import BaseRepository, CursorPage


class UsageRecordRepository(BaseRepository[UsageRecord]):
    """Repository for UsageRecord CRUD and aggregate queries."""

    model = UsageRecord

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    # ── Lookups ───────────────────────────────────────────────────────────────

    async def get_by_request_id(
        self,
        organization_id: uuid.UUID,
        request_id: str,
    ) -> UsageRecord | None:
        """Return the active record for (org, request_id), or None.

        Uses the unique index backing uq_usage_records_org_request_id —
        this is the entire idempotency check.
        """
        stmt = self._active_query().where(
            and_(
                UsageRecord.organization_id == organization_id,
                UsageRecord.request_id == request_id,
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_org(
        self,
        organization_id: uuid.UUID,
        *,
        limit: int = 20,
        cursor: str | None = None,
        order: str = "desc",
    ) -> CursorPage[UsageRecord]:
        """Return a cursor-paginated page of usage records for an org."""
        return await self.list_page(
            limit=limit,
            cursor=cursor,
            order=order,
            extra_filters=UsageRecord.organization_id == organization_id,
        )

    # ── Aggregates ────────────────────────────────────────────────────────────
    # All group by currency alongside the requested dimension — summing
    # across currencies would silently produce a meaningless total in any
    # multi-currency organization (the same fix applied to EP-09's
    # UsageCostRecordRepository after REV-02).

    async def get_daily_totals(
        self,
        organization_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> list[dict]:
        """Group by calendar date (of request_timestamp) and currency."""
        day = func.date(UsageRecord.request_timestamp)
        stmt = (
            select(
                day.label("usage_date"),
                UsageRecord.currency,
                func.coalesce(func.sum(UsageRecord.cost), Decimal(0)).label("total_cost"),
                func.coalesce(func.sum(UsageRecord.total_tokens), 0).label("total_tokens"),
                func.count(UsageRecord.id).label("record_count"),
            )
            .where(
                and_(
                    UsageRecord.organization_id == organization_id,
                    day >= start_date,
                    day <= end_date,
                    UsageRecord.deleted_at.is_(None),
                )
            )
            .group_by(day, UsageRecord.currency)
            .order_by(day.asc())
        )
        result = await self._session.execute(stmt)
        return [
            {
                "usage_date": row.usage_date,
                "currency": row.currency,
                "total_cost": row.total_cost or Decimal(0),
                "total_tokens": row.total_tokens or 0,
                "record_count": row.record_count or 0,
            }
            for row in result.all()
        ]

    async def get_monthly_totals(
        self,
        organization_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> list[dict]:
        """Group by calendar month (of request_timestamp) and currency."""
        month = func.date_trunc("month", UsageRecord.request_timestamp)
        day = func.date(UsageRecord.request_timestamp)
        stmt = (
            select(
                month.label("usage_month"),
                UsageRecord.currency,
                func.coalesce(func.sum(UsageRecord.cost), Decimal(0)).label("total_cost"),
                func.coalesce(func.sum(UsageRecord.total_tokens), 0).label("total_tokens"),
                func.count(UsageRecord.id).label("record_count"),
            )
            .where(
                and_(
                    UsageRecord.organization_id == organization_id,
                    day >= start_date,
                    day <= end_date,
                    UsageRecord.deleted_at.is_(None),
                )
            )
            .group_by(month, UsageRecord.currency)
            .order_by(month.asc())
        )
        result = await self._session.execute(stmt)
        return [
            {
                "usage_month": row.usage_month,
                "currency": row.currency,
                "total_cost": row.total_cost or Decimal(0),
                "total_tokens": row.total_tokens or 0,
                "record_count": row.record_count or 0,
            }
            for row in result.all()
        ]

    async def get_project_month_to_date_total(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        *,
        as_of: date,
    ) -> Decimal:
        """Sum of `cost` for this project from the 1st of `as_of`'s month
        through `as_of`, inclusive — the "month-to-date spend" a
        `Project.budget` is compared against (EP-19.3). Ignores currency
        mixing (sums whatever currency each record was ingested in) since
        `UsageIngestionService` doesn't convert currencies today; a project
        billed in more than one currency would need real FX conversion
        before this number means anything, which is out of scope here and
        stated rather than silently wrong."""
        month_start = as_of.replace(day=1)
        day = func.date(UsageRecord.request_timestamp)
        stmt = select(func.coalesce(func.sum(UsageRecord.cost), Decimal(0))).where(
            and_(
                UsageRecord.organization_id == organization_id,
                UsageRecord.project_id == project_id,
                day >= month_start,
                day <= as_of,
                UsageRecord.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one() or Decimal(0)

    async def get_totals_by_provider(
        self,
        organization_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> list[dict]:
        """Group by provider and currency."""
        day = func.date(UsageRecord.request_timestamp)
        stmt = (
            select(
                UsageRecord.provider,
                UsageRecord.currency,
                func.coalesce(func.sum(UsageRecord.cost), Decimal(0)).label("total_cost"),
                func.coalesce(func.sum(UsageRecord.total_tokens), 0).label("total_tokens"),
                func.count(UsageRecord.id).label("record_count"),
            )
            .where(
                and_(
                    UsageRecord.organization_id == organization_id,
                    day >= start_date,
                    day <= end_date,
                    UsageRecord.deleted_at.is_(None),
                )
            )
            .group_by(UsageRecord.provider, UsageRecord.currency)
            .order_by(func.sum(UsageRecord.cost).desc())
        )
        result = await self._session.execute(stmt)
        return [
            {
                "provider": row.provider,
                "currency": row.currency,
                "total_cost": row.total_cost or Decimal(0),
                "total_tokens": row.total_tokens or 0,
                "record_count": row.record_count or 0,
            }
            for row in result.all()
        ]

    async def get_totals_by_model(
        self,
        organization_id: uuid.UUID,
        start_date: date,
        end_date: date,
        limit: int | None = None,
    ) -> list[dict]:
        """Group by provider+model and currency. SQL LIMIT, not Python slicing."""
        day = func.date(UsageRecord.request_timestamp)
        stmt = (
            select(
                UsageRecord.provider,
                UsageRecord.model,
                UsageRecord.currency,
                func.coalesce(func.sum(UsageRecord.cost), Decimal(0)).label("total_cost"),
                func.coalesce(func.sum(UsageRecord.total_tokens), 0).label("total_tokens"),
                func.count(UsageRecord.id).label("record_count"),
            )
            .where(
                and_(
                    UsageRecord.organization_id == organization_id,
                    day >= start_date,
                    day <= end_date,
                    UsageRecord.deleted_at.is_(None),
                )
            )
            .group_by(UsageRecord.provider, UsageRecord.model, UsageRecord.currency)
            .order_by(func.sum(UsageRecord.cost).desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self._session.execute(stmt)
        return [
            {
                "provider": row.provider,
                "model": row.model,
                "currency": row.currency,
                "total_cost": row.total_cost or Decimal(0),
                "total_tokens": row.total_tokens or 0,
                "record_count": row.record_count or 0,
            }
            for row in result.all()
        ]
