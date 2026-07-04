"""AggregationService — F-054 (EP-09).

Builds and refreshes DailyCostSummary records from UsageCostRecord data.
Supports both single-day builds and multi-day range rebuilds.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.mixins import uuid7
from app.models.daily_cost_summary import DailyCostSummary
from app.models.usage_cost_record import UsageCostRecord
from app.repositories.daily_cost_summary_repository import DailyCostSummaryRepository

log = structlog.get_logger(__name__)


class AggregationService:
    """Builds and refreshes DailyCostSummary records from UsageCostRecord data.

    Uses raw SQL aggregation for efficiency, then upserts the results.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._summary_repo = DailyCostSummaryRepository(session)

    async def build_daily_summaries(
        self,
        organization_id: uuid.UUID,
        target_date: date,
    ) -> list[DailyCostSummary]:
        """Aggregate UsageCostRecords for org+date into DailyCostSummary records.

        Groups by (organization_id, project_id, provider, model, currency).
        Upserts into daily_cost_summaries.
        Returns list of upserted summaries.
        """
        log.info(
            "building_daily_summaries",
            organization_id=str(organization_id),
            target_date=str(target_date),
        )

        # Aggregate cost records for this org + date
        stmt = (
            select(
                UsageCostRecord.organization_id,
                UsageCostRecord.project_id,
                UsageCostRecord.provider,
                UsageCostRecord.model,
                UsageCostRecord.currency,
                func.coalesce(func.sum(UsageCostRecord.prompt_tokens), 0).label(
                    "total_prompt_tokens"
                ),
                func.coalesce(func.sum(UsageCostRecord.completion_tokens), 0).label(
                    "total_completion_tokens"
                ),
                func.sum(UsageCostRecord.cached_tokens).label("total_cached_tokens"),
                func.coalesce(func.sum(UsageCostRecord.total_tokens), 0).label("total_tokens"),
                func.count(UsageCostRecord.id).label("total_requests"),
                func.coalesce(func.sum(UsageCostRecord.total_cost), Decimal(0)).label("total_cost"),
                func.coalesce(func.sum(UsageCostRecord.prompt_cost), Decimal(0)).label(
                    "total_prompt_cost"
                ),
                func.coalesce(func.sum(UsageCostRecord.completion_cost), Decimal(0)).label(
                    "total_completion_cost"
                ),
                func.sum(UsageCostRecord.cached_cost).label("total_cached_cost"),
                func.count(UsageCostRecord.id).label("event_count"),
            )
            .where(
                and_(
                    UsageCostRecord.organization_id == organization_id,
                    UsageCostRecord.usage_date == target_date,
                    UsageCostRecord.deleted_at.is_(None),
                )
            )
            .group_by(
                UsageCostRecord.organization_id,
                UsageCostRecord.project_id,
                UsageCostRecord.provider,
                UsageCostRecord.model,
                UsageCostRecord.currency,
            )
        )

        result = await self._session.execute(stmt)
        rows = result.all()

        summaries: list[DailyCostSummary] = []
        for row in rows:
            now = datetime.now(UTC)

            summary = DailyCostSummary()
            summary.id = uuid7()
            summary.created_at = now
            summary.updated_at = now
            summary.organization_id = row.organization_id
            summary.project_id = row.project_id
            summary.provider = row.provider
            summary.model = row.model
            summary.currency = row.currency
            summary.summary_date = target_date
            summary.total_prompt_tokens = row.total_prompt_tokens or 0
            summary.total_completion_tokens = row.total_completion_tokens or 0
            summary.total_cached_tokens = row.total_cached_tokens
            summary.total_tokens = row.total_tokens or 0
            summary.total_requests = row.total_requests or 0
            summary.total_cost = row.total_cost or Decimal(0)
            summary.total_prompt_cost = row.total_prompt_cost or Decimal(0)
            summary.total_completion_cost = row.total_completion_cost or Decimal(0)
            summary.total_cached_cost = row.total_cached_cost
            summary.event_count = row.event_count or 0

            upserted = await self._summary_repo.upsert(summary)
            summaries.append(upserted)

        log.info(
            "daily_summaries_built",
            organization_id=str(organization_id),
            target_date=str(target_date),
            summary_count=len(summaries),
        )
        return summaries

    async def rebuild_range(
        self,
        organization_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> int:
        """Rebuild daily summaries for an entire date range.

        Iterates day by day and calls build_daily_summaries for each.
        Returns total count of summaries built across all days.
        """
        log.info(
            "rebuilding_summary_range",
            organization_id=str(organization_id),
            start_date=str(start_date),
            end_date=str(end_date),
        )

        total_count = 0
        current = start_date
        while current <= end_date:
            day_summaries = await self.build_daily_summaries(organization_id, current)
            total_count += len(day_summaries)
            current = current + timedelta(days=1)

        log.info(
            "summary_range_rebuilt",
            organization_id=str(organization_id),
            total_summaries=total_count,
        )
        return total_count
