"""DailyCostSummaryRepository — F-054 (EP-09).

Provides upsert and date-range query methods for daily cost summaries.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import cast

from sqlalchemy import Table, and_, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.daily_cost_summary import DailyCostSummary
from app.repositories.base_repository import BaseRepository


class DailyCostSummaryRepository(BaseRepository[DailyCostSummary]):
    """Repository for DailyCostSummary records."""

    model = DailyCostSummary

    async def upsert(self, summary: DailyCostSummary) -> DailyCostSummary:
        """Insert or update using ON CONFLICT on uq_daily_cost_summaries.

        If a summary already exists for the same (org, project, provider,
        model, currency, date) combination, all aggregated values are updated.
        """
        values = {
            "id": summary.id,
            "created_at": summary.created_at,
            "updated_at": summary.updated_at,
            "deleted_at": summary.deleted_at,
            "deleted_by": summary.deleted_by,
            "organization_id": summary.organization_id,
            "project_id": summary.project_id,
            "provider": summary.provider,
            "model": summary.model,
            "currency": summary.currency,
            "summary_date": summary.summary_date,
            "total_prompt_tokens": summary.total_prompt_tokens,
            "total_completion_tokens": summary.total_completion_tokens,
            "total_cached_tokens": summary.total_cached_tokens,
            "total_tokens": summary.total_tokens,
            "total_requests": summary.total_requests,
            "total_cost": summary.total_cost,
            "total_prompt_cost": summary.total_prompt_cost,
            "total_completion_cost": summary.total_completion_cost,
            "total_cached_cost": summary.total_cached_cost,
            "event_count": summary.event_count,
        }

        # __table__ is typed as the broader FromClause by SQLAlchemy's
        # declarative base but is always a concrete Table at runtime for this
        # model; cast so pg_insert() sees the narrower type it requires.
        stmt = pg_insert(cast("Table", DailyCostSummary.__table__)).values(**values)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_daily_cost_summaries",
            set_={
                "total_prompt_tokens": stmt.excluded.total_prompt_tokens,
                "total_completion_tokens": stmt.excluded.total_completion_tokens,
                "total_cached_tokens": stmt.excluded.total_cached_tokens,
                "total_tokens": stmt.excluded.total_tokens,
                "total_requests": stmt.excluded.total_requests,
                "total_cost": stmt.excluded.total_cost,
                "total_prompt_cost": stmt.excluded.total_prompt_cost,
                "total_completion_cost": stmt.excluded.total_completion_cost,
                "total_cached_cost": stmt.excluded.total_cached_cost,
                "event_count": stmt.excluded.event_count,
                "updated_at": func.now(),
            },
        )
        await self._session.execute(stmt)
        await self._session.flush()

        # Return the persisted summary
        result = await self._session.execute(
            select(DailyCostSummary).where(
                and_(
                    DailyCostSummary.organization_id == summary.organization_id,
                    DailyCostSummary.provider == summary.provider,
                    DailyCostSummary.model == summary.model,
                    DailyCostSummary.currency == summary.currency,
                    DailyCostSummary.summary_date == summary.summary_date,
                    (
                        DailyCostSummary.project_id == summary.project_id
                        if summary.project_id is not None
                        else DailyCostSummary.project_id.is_(None)
                    ),
                    DailyCostSummary.deleted_at.is_(None),
                )
            )
        )
        persisted = result.scalar_one_or_none()
        return persisted if persisted is not None else summary

    async def get_for_date_range(
        self,
        organization_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> list[DailyCostSummary]:
        """Return all summaries for org in date range, ordered by date."""
        stmt = (
            self._active_query()
            .where(
                and_(
                    DailyCostSummary.organization_id == organization_id,
                    DailyCostSummary.summary_date >= start_date,
                    DailyCostSummary.summary_date <= end_date,
                )
            )
            .order_by(DailyCostSummary.summary_date.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_provider(
        self,
        organization_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> list[DailyCostSummary]:
        """Return summaries filtered by org and date range, ordered by date then provider."""
        stmt = (
            self._active_query()
            .where(
                and_(
                    DailyCostSummary.organization_id == organization_id,
                    DailyCostSummary.summary_date >= start_date,
                    DailyCostSummary.summary_date <= end_date,
                )
            )
            .order_by(DailyCostSummary.summary_date.asc(), DailyCostSummary.provider)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_model(
        self,
        organization_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> list[DailyCostSummary]:
        """Return summaries filtered by org and date range, ordered by date then model."""
        stmt = (
            self._active_query()
            .where(
                and_(
                    DailyCostSummary.organization_id == organization_id,
                    DailyCostSummary.summary_date >= start_date,
                    DailyCostSummary.summary_date <= end_date,
                )
            )
            .order_by(DailyCostSummary.summary_date.asc(), DailyCostSummary.model)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
