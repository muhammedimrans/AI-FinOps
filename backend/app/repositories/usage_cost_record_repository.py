"""UsageCostRecordRepository — F-051 (EP-09).

Provides upsert and aggregation queries for cost records.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any, cast

import structlog
from sqlalchemy import Table, and_, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.usage_cost_record import UsageCostRecord
from app.models.usage_event import UsageEvent
from app.repositories.base_repository import BaseRepository

log = structlog.get_logger(__name__)


class UsageCostRecordRepository(BaseRepository[UsageCostRecord]):
    """Repository for UsageCostRecord records."""

    model = UsageCostRecord

    async def get_by_event(self, usage_event_id: uuid.UUID) -> UsageCostRecord | None:
        """Get the cost record for a specific usage event."""
        stmt = self._active_query().where(UsageCostRecord.usage_event_id == usage_event_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert(self, record: UsageCostRecord) -> UsageCostRecord:
        """Insert or update using ON CONFLICT on uq_usage_cost_records_event.

        If a cost record already exists for the same usage_event_id, all
        cost fields are updated. This supports recalculation when pricing
        changes.
        """
        values = {
            "id": record.id,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "deleted_at": record.deleted_at,
            "deleted_by": record.deleted_by,
            "usage_event_id": record.usage_event_id,
            "organization_id": record.organization_id,
            "project_id": record.project_id,
            "provider_connection_id": record.provider_connection_id,
            "model_pricing_id": record.model_pricing_id,
            "provider": record.provider,
            "model": record.model,
            "currency": record.currency,
            "usage_date": record.usage_date,
            "prompt_tokens": record.prompt_tokens,
            "completion_tokens": record.completion_tokens,
            "cached_tokens": record.cached_tokens,
            "total_tokens": record.total_tokens,
            "prompt_cost": record.prompt_cost,
            "completion_cost": record.completion_cost,
            "cached_cost": record.cached_cost,
            "total_cost": record.total_cost,
            "calculation_version": record.calculation_version,
        }

        # __table__ is typed as the broader FromClause by SQLAlchemy's
        # declarative base but is always a concrete Table at runtime for this
        # model; cast so pg_insert() sees the narrower type it requires.
        stmt = pg_insert(cast("Table", UsageCostRecord.__table__)).values(**values)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_usage_cost_records_event",
            set_={
                "model_pricing_id": stmt.excluded.model_pricing_id,
                "currency": stmt.excluded.currency,
                "usage_date": stmt.excluded.usage_date,
                "prompt_tokens": stmt.excluded.prompt_tokens,
                "completion_tokens": stmt.excluded.completion_tokens,
                "cached_tokens": stmt.excluded.cached_tokens,
                "total_tokens": stmt.excluded.total_tokens,
                "prompt_cost": stmt.excluded.prompt_cost,
                "completion_cost": stmt.excluded.completion_cost,
                "cached_cost": stmt.excluded.cached_cost,
                "total_cost": stmt.excluded.total_cost,
                "calculation_version": stmt.excluded.calculation_version,
                "updated_at": func.now(),
            },
        )
        await self._session.execute(stmt)
        await self._session.flush()

        # Return the persisted record
        result = await self.get_by_event(record.usage_event_id)
        if result is None:
            # Should not happen; return the original object
            log.warning("upsert_cost_record_not_found", event_id=str(record.usage_event_id))
            return record
        return result

    async def get_totals_by_connection(
        self, provider_connection_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        """All-time cost totals for one connection, grouped by currency (EP-23.3).

        Powers "Estimated Cost Imported" on the Provider Connections page.
        No date range — this is a lifetime total for the connection, unlike
        ``get_totals_by_org``'s period-scoped variant. Grouped by currency
        for the same reason that one is: USD and EUR must never be summed
        together.
        """
        stmt = (
            select(
                UsageCostRecord.currency,
                func.coalesce(func.sum(UsageCostRecord.total_cost), Decimal(0)).label("total_cost"),
                func.count(UsageCostRecord.id).label("record_count"),
            )
            .where(
                and_(
                    UsageCostRecord.provider_connection_id == provider_connection_id,
                    UsageCostRecord.deleted_at.is_(None),
                )
            )
            .group_by(UsageCostRecord.currency)
            .order_by(UsageCostRecord.currency)
        )
        result = await self._session.execute(stmt)
        return [
            {
                "currency": row.currency,
                "total_cost": row.total_cost or Decimal(0),
                "record_count": row.record_count or 0,
            }
            for row in result.all()
        ]

    @staticmethod
    def _dimension_filters(
        *,
        project_id: uuid.UUID | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> list[Any]:
        """Optional equality filters shared by every breakdown query below (EP-24.1).

        Lets callers narrow any breakdown to one project/provider/model
        without a second query shape — the same grouped-aggregate SQL is
        reused, just with an extra ``WHERE`` clause appended.
        """
        filters: list[Any] = []
        if project_id is not None:
            filters.append(UsageCostRecord.project_id == project_id)
        if provider is not None:
            filters.append(UsageCostRecord.provider == provider)
        if model is not None:
            filters.append(UsageCostRecord.model == model)
        return filters

    async def get_totals_by_org(
        self,
        organization_id: uuid.UUID,
        start_date: date,
        end_date: date,
        *,
        project_id: uuid.UUID | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> list[dict[str, Any]]:
        """Sum total_cost, total_tokens, request count for org + date range.

        Groups by currency so that USD and EUR totals are never summed together.
        Returns one dict per currency. An empty list is returned when there are
        no cost records for the given org and date range. Optional
        project/provider/model filters narrow the same query (EP-24.1).
        """
        stmt = (
            select(
                UsageCostRecord.currency,
                func.coalesce(func.sum(UsageCostRecord.total_cost), Decimal(0)).label("total_cost"),
                func.coalesce(func.sum(UsageCostRecord.total_tokens), 0).label("total_tokens"),
                func.coalesce(func.sum(UsageCostRecord.prompt_tokens), 0).label(
                    "total_prompt_tokens"
                ),
                func.coalesce(func.sum(UsageCostRecord.completion_tokens), 0).label(
                    "total_completion_tokens"
                ),
                func.count(UsageCostRecord.id).label("record_count"),
            )
            .where(
                and_(
                    UsageCostRecord.organization_id == organization_id,
                    UsageCostRecord.usage_date >= start_date,
                    UsageCostRecord.usage_date <= end_date,
                    UsageCostRecord.deleted_at.is_(None),
                    *self._dimension_filters(project_id=project_id, provider=provider, model=model),
                )
            )
            .group_by(UsageCostRecord.currency)
            .order_by(UsageCostRecord.currency)
        )
        result = await self._session.execute(stmt)
        return [
            {
                "currency": row.currency,
                "total_cost": row.total_cost or Decimal(0),
                "total_tokens": row.total_tokens or 0,
                "total_prompt_tokens": row.total_prompt_tokens or 0,
                "total_completion_tokens": row.total_completion_tokens or 0,
                "record_count": row.record_count or 0,
            }
            for row in result.all()
        ]

    async def get_totals_by_provider(
        self,
        organization_id: uuid.UUID,
        start_date: date,
        end_date: date,
        *,
        project_id: uuid.UUID | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> list[dict[str, Any]]:
        """Group by provider, sum costs and tokens.

        ``model_count`` is the number of distinct models seen for that
        provider in the period — computed via ``COUNT(DISTINCT model)`` in
        the same query rather than a second round-trip (EP-24.1).
        """
        stmt = (
            select(
                UsageCostRecord.provider,
                UsageCostRecord.currency,
                func.coalesce(func.sum(UsageCostRecord.total_cost), Decimal(0)).label("total_cost"),
                func.coalesce(func.sum(UsageCostRecord.prompt_cost), Decimal(0)).label(
                    "total_prompt_cost"
                ),
                func.coalesce(func.sum(UsageCostRecord.completion_cost), Decimal(0)).label(
                    "total_completion_cost"
                ),
                func.coalesce(func.sum(UsageCostRecord.total_tokens), 0).label("total_tokens"),
                func.coalesce(func.sum(UsageCostRecord.prompt_tokens), 0).label(
                    "total_prompt_tokens"
                ),
                func.coalesce(func.sum(UsageCostRecord.completion_tokens), 0).label(
                    "total_completion_tokens"
                ),
                func.count(UsageCostRecord.id).label("record_count"),
                func.count(func.distinct(UsageCostRecord.model)).label("model_count"),
            )
            .where(
                and_(
                    UsageCostRecord.organization_id == organization_id,
                    UsageCostRecord.usage_date >= start_date,
                    UsageCostRecord.usage_date <= end_date,
                    UsageCostRecord.deleted_at.is_(None),
                    *self._dimension_filters(project_id=project_id, provider=provider, model=model),
                )
            )
            .group_by(UsageCostRecord.provider, UsageCostRecord.currency)
            .order_by(func.sum(UsageCostRecord.total_cost).desc())
        )
        result = await self._session.execute(stmt)
        return [
            {
                "provider": row.provider,
                "currency": row.currency,
                "total_cost": row.total_cost or Decimal(0),
                "total_prompt_cost": row.total_prompt_cost or Decimal(0),
                "total_completion_cost": row.total_completion_cost or Decimal(0),
                "total_tokens": row.total_tokens or 0,
                "total_prompt_tokens": row.total_prompt_tokens or 0,
                "total_completion_tokens": row.total_completion_tokens or 0,
                "record_count": row.record_count or 0,
                "model_count": row.model_count or 0,
            }
            for row in result.all()
        ]

    async def get_totals_by_model(
        self,
        organization_id: uuid.UUID,
        start_date: date,
        end_date: date,
        limit: int | None = None,
        *,
        project_id: uuid.UUID | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> list[dict[str, Any]]:
        """Group by model, sum costs and tokens.

        If ``limit`` is provided the query applies SQL LIMIT, avoiding the
        need for Python-side slicing in callers such as ``get_top_models``.
        """
        stmt = (
            select(
                UsageCostRecord.provider,
                UsageCostRecord.model,
                UsageCostRecord.currency,
                func.coalesce(func.sum(UsageCostRecord.total_cost), Decimal(0)).label("total_cost"),
                func.coalesce(func.sum(UsageCostRecord.prompt_cost), Decimal(0)).label(
                    "total_prompt_cost"
                ),
                func.coalesce(func.sum(UsageCostRecord.completion_cost), Decimal(0)).label(
                    "total_completion_cost"
                ),
                func.coalesce(func.sum(UsageCostRecord.total_tokens), 0).label("total_tokens"),
                func.coalesce(func.sum(UsageCostRecord.prompt_tokens), 0).label(
                    "total_prompt_tokens"
                ),
                func.coalesce(func.sum(UsageCostRecord.completion_tokens), 0).label(
                    "total_completion_tokens"
                ),
                func.count(UsageCostRecord.id).label("record_count"),
            )
            .where(
                and_(
                    UsageCostRecord.organization_id == organization_id,
                    UsageCostRecord.usage_date >= start_date,
                    UsageCostRecord.usage_date <= end_date,
                    UsageCostRecord.deleted_at.is_(None),
                    *self._dimension_filters(project_id=project_id, provider=provider, model=model),
                )
            )
            .group_by(UsageCostRecord.provider, UsageCostRecord.model, UsageCostRecord.currency)
            .order_by(func.sum(UsageCostRecord.total_cost).desc())
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
                "total_prompt_cost": row.total_prompt_cost or Decimal(0),
                "total_completion_cost": row.total_completion_cost or Decimal(0),
                "total_tokens": row.total_tokens or 0,
                "total_prompt_tokens": row.total_prompt_tokens or 0,
                "total_completion_tokens": row.total_completion_tokens or 0,
                "record_count": row.record_count or 0,
            }
            for row in result.all()
        ]

    async def get_totals_by_project(
        self,
        organization_id: uuid.UUID,
        start_date: date,
        end_date: date,
        limit: int | None = None,
        *,
        project_id: uuid.UUID | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> list[dict[str, Any]]:
        """Group by project_id, sum costs and tokens.

        If ``limit`` is provided the query applies SQL LIMIT, avoiding the
        need for Python-side slicing in callers such as ``get_top_projects``.
        """
        stmt = (
            select(
                UsageCostRecord.project_id,
                UsageCostRecord.currency,
                func.coalesce(func.sum(UsageCostRecord.total_cost), Decimal(0)).label("total_cost"),
                func.coalesce(func.sum(UsageCostRecord.total_tokens), 0).label("total_tokens"),
                func.count(UsageCostRecord.id).label("record_count"),
            )
            .where(
                and_(
                    UsageCostRecord.organization_id == organization_id,
                    UsageCostRecord.usage_date >= start_date,
                    UsageCostRecord.usage_date <= end_date,
                    UsageCostRecord.deleted_at.is_(None),
                    *self._dimension_filters(project_id=project_id, provider=provider, model=model),
                )
            )
            .group_by(UsageCostRecord.project_id, UsageCostRecord.currency)
            .order_by(func.sum(UsageCostRecord.total_cost).desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self._session.execute(stmt)
        return [
            {
                "project_id": row.project_id,
                "currency": row.currency,
                "total_cost": row.total_cost or Decimal(0),
                "total_tokens": row.total_tokens or 0,
                "record_count": row.record_count or 0,
            }
            for row in result.all()
        ]

    async def get_daily_trend(
        self,
        organization_id: uuid.UUID,
        start_date: date,
        end_date: date,
        *,
        project_id: uuid.UUID | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> list[dict[str, Any]]:
        """Group by usage_date, sum costs. Returns date-ordered list.

        ``total_prompt_tokens``/``total_completion_tokens`` (EP-24.1) power
        the Token Trend chart's input/output split — the same columns
        ``get_totals_by_provider``/``get_totals_by_model`` already summed,
        just not previously carried through this one query.
        """
        stmt = (
            select(
                UsageCostRecord.usage_date,
                UsageCostRecord.currency,
                func.coalesce(func.sum(UsageCostRecord.total_cost), Decimal(0)).label("total_cost"),
                func.coalesce(func.sum(UsageCostRecord.prompt_cost), Decimal(0)).label(
                    "total_prompt_cost"
                ),
                func.coalesce(func.sum(UsageCostRecord.completion_cost), Decimal(0)).label(
                    "total_completion_cost"
                ),
                func.coalesce(func.sum(UsageCostRecord.total_tokens), 0).label("total_tokens"),
                func.coalesce(func.sum(UsageCostRecord.prompt_tokens), 0).label(
                    "total_prompt_tokens"
                ),
                func.coalesce(func.sum(UsageCostRecord.completion_tokens), 0).label(
                    "total_completion_tokens"
                ),
                func.count(UsageCostRecord.id).label("record_count"),
            )
            .where(
                and_(
                    UsageCostRecord.organization_id == organization_id,
                    UsageCostRecord.usage_date >= start_date,
                    UsageCostRecord.usage_date <= end_date,
                    UsageCostRecord.deleted_at.is_(None),
                    *self._dimension_filters(project_id=project_id, provider=provider, model=model),
                )
            )
            .group_by(UsageCostRecord.usage_date, UsageCostRecord.currency)
            .order_by(UsageCostRecord.usage_date.asc())
        )
        result = await self._session.execute(stmt)
        return [
            {
                "usage_date": row.usage_date,
                "currency": row.currency,
                "total_cost": row.total_cost or Decimal(0),
                "total_prompt_cost": row.total_prompt_cost or Decimal(0),
                "total_completion_cost": row.total_completion_cost or Decimal(0),
                "total_tokens": row.total_tokens or 0,
                "total_prompt_tokens": row.total_prompt_tokens or 0,
                "total_completion_tokens": row.total_completion_tokens or 0,
                "record_count": row.record_count or 0,
            }
            for row in result.all()
        ]

    async def get_heatmap(
        self,
        organization_id: uuid.UUID,
        start_date: date,
        end_date: date,
        *,
        project_id: uuid.UUID | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> list[dict[str, Any]]:
        """Cost-weighted hour-of-day x day-of-week grid (EP-24.1).

        ``UsageCostRecord.usage_date`` has no time-of-day component, so an
        hour-of-day breakdown requires the one column that does:
        ``UsageEvent.timestamp``. Joined via the existing
        ``usage_event_id`` FK rather than adding a redundant timestamp
        column to ``UsageCostRecord`` — one join, still a single grouped
        aggregate query, no Python-side bucketing of raw rows.
        """
        stmt = (
            select(
                func.extract("hour", UsageEvent.timestamp).label("hour_of_day"),
                func.extract("dow", UsageEvent.timestamp).label("day_of_week"),
                UsageCostRecord.currency,
                func.coalesce(func.sum(UsageCostRecord.total_cost), Decimal(0)).label("total_cost"),
                func.coalesce(func.sum(UsageCostRecord.total_tokens), 0).label("total_tokens"),
                func.count(UsageCostRecord.id).label("record_count"),
            )
            .join(UsageEvent, UsageCostRecord.usage_event_id == UsageEvent.id)
            .where(
                and_(
                    UsageCostRecord.organization_id == organization_id,
                    UsageCostRecord.usage_date >= start_date,
                    UsageCostRecord.usage_date <= end_date,
                    UsageCostRecord.deleted_at.is_(None),
                    *self._dimension_filters(project_id=project_id, provider=provider, model=model),
                )
            )
            .group_by("hour_of_day", "day_of_week", UsageCostRecord.currency)
            .order_by("day_of_week", "hour_of_day")
        )
        result = await self._session.execute(stmt)
        return [
            {
                "hour_of_day": int(row.hour_of_day),
                "day_of_week": int(row.day_of_week),
                "currency": row.currency,
                "total_cost": row.total_cost or Decimal(0),
                "total_tokens": row.total_tokens or 0,
                "record_count": row.record_count or 0,
            }
            for row in result.all()
        ]
