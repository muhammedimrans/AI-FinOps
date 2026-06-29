"""ProviderUsageSummaryRepository — F-045 (EP-08)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import and_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.mixins import uuid7
from app.models.provider_usage_summary import ProviderUsageSummary
from app.repositories.base_repository import BaseRepository, CursorPage


class ProviderUsageSummaryRepository(BaseRepository[ProviderUsageSummary]):
    """Repository for ProviderUsageSummary with upsert support."""

    model = ProviderUsageSummary

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def upsert(self, summary: ProviderUsageSummary) -> ProviderUsageSummary:
        """Insert or update a summary using the unique period constraint."""
        stmt = (
            pg_insert(ProviderUsageSummary)
            .values(
                id=summary.id if summary.id else uuid7(),
                organization_id=summary.organization_id,
                project_id=summary.project_id,
                provider=summary.provider,
                model=summary.model,
                period_start=summary.period_start,
                period_end=summary.period_end,
                total_requests=summary.total_requests,
                total_prompt_tokens=summary.total_prompt_tokens,
                total_completion_tokens=summary.total_completion_tokens,
                total_cached_tokens=summary.total_cached_tokens,
                total_tokens=summary.total_tokens,
                event_count=summary.event_count,
            )
            .on_conflict_do_update(
                constraint="uq_provider_usage_summaries",
                set_={
                    "total_requests": summary.total_requests,
                    "total_prompt_tokens": summary.total_prompt_tokens,
                    "total_completion_tokens": summary.total_completion_tokens,
                    "total_cached_tokens": summary.total_cached_tokens,
                    "total_tokens": summary.total_tokens,
                    "event_count": summary.event_count,
                },
            )
            .returning(ProviderUsageSummary.id)
        )
        result = await self._session.execute(stmt)
        row = result.fetchone()
        if row:
            summary.id = row[0]
        return summary

    async def list_by_org(
        self,
        organization_id: uuid.UUID,
        *,
        limit: int = 20,
        cursor: str | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> CursorPage[ProviderUsageSummary]:
        filters = [ProviderUsageSummary.organization_id == organization_id]
        if provider:
            filters.append(ProviderUsageSummary.provider == provider)
        if model:
            filters.append(ProviderUsageSummary.model == model)
        return await self.list_page(
            limit=limit,
            cursor=cursor,
            order="desc",
            extra_filters=and_(*filters),
        )

    async def list_by_period(
        self,
        organization_id: uuid.UUID,
        *,
        start: datetime,
        end: datetime,
        provider: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> CursorPage[ProviderUsageSummary]:
        filters = [
            ProviderUsageSummary.organization_id == organization_id,
            ProviderUsageSummary.period_start >= start,
            ProviderUsageSummary.period_end <= end,
        ]
        if provider:
            filters.append(ProviderUsageSummary.provider == provider)
        return await self.list_page(
            limit=limit,
            cursor=cursor,
            order="desc",
            extra_filters=and_(*filters),
        )
