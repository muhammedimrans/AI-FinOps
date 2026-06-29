"""AnalyticsService — F-053 (EP-09).

Read-only analytics over cost records and daily summaries.
Provides breakdowns by provider, model, project, and date.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from app.repositories.daily_cost_summary_repository import DailyCostSummaryRepository
    from app.repositories.usage_cost_record_repository import UsageCostRecordRepository

log = structlog.get_logger(__name__)


class AnalyticsService:
    """Read-only analytics over cost records and usage events.

    Uses UsageCostRecordRepository for detailed breakdowns and
    DailyCostSummaryRepository for pre-aggregated summaries.
    """

    def __init__(
        self,
        cost_record_repo: UsageCostRecordRepository,
        daily_summary_repo: DailyCostSummaryRepository,
    ) -> None:
        self._cost_repo = cost_record_repo
        self._summary_repo = daily_summary_repo

    async def get_usage_summary(
        self,
        organization_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> dict:
        """Total tokens, requests, events for org in date range."""
        totals = await self._cost_repo.get_totals_by_org(organization_id, start_date, end_date)
        return {
            "organization_id": str(organization_id),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "total_tokens": totals.get("total_tokens", 0),
            "total_prompt_tokens": totals.get("total_prompt_tokens", 0),
            "total_completion_tokens": totals.get("total_completion_tokens", 0),
            "total_requests": totals.get("record_count", 0),
            "event_count": totals.get("record_count", 0),
        }

    async def get_cost_summary(
        self,
        organization_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> dict:
        """Total costs by currency for org in date range."""
        totals = await self._cost_repo.get_totals_by_org(organization_id, start_date, end_date)
        return {
            "organization_id": str(organization_id),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "total_cost": totals.get("total_cost", Decimal(0)),
            "total_tokens": totals.get("total_tokens", 0),
            "record_count": totals.get("record_count", 0),
        }

    async def get_provider_breakdown(
        self,
        organization_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> list[dict]:
        """Per-provider cost and token breakdown."""
        return await self._cost_repo.get_totals_by_provider(organization_id, start_date, end_date)

    async def get_model_breakdown(
        self,
        organization_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> list[dict]:
        """Per-model cost and token breakdown."""
        return await self._cost_repo.get_totals_by_model(organization_id, start_date, end_date)

    async def get_project_breakdown(
        self,
        organization_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> list[dict]:
        """Per-project cost and token breakdown."""
        return await self._cost_repo.get_totals_by_project(organization_id, start_date, end_date)

    async def get_daily_trend(
        self,
        organization_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> list[dict]:
        """Day-by-day cost totals ordered by date."""
        return await self._cost_repo.get_daily_trend(organization_id, start_date, end_date)

    async def get_top_models(
        self,
        organization_id: uuid.UUID,
        start_date: date,
        end_date: date,
        limit: int = 10,
    ) -> list[dict]:
        """Top N models by total cost."""
        all_models = await self._cost_repo.get_totals_by_model(organization_id, start_date, end_date)
        # Already sorted by total_cost desc from the repository
        return all_models[:limit]

    async def get_top_projects(
        self,
        organization_id: uuid.UUID,
        start_date: date,
        end_date: date,
        limit: int = 10,
    ) -> list[dict]:
        """Top N projects by total cost."""
        all_projects = await self._cost_repo.get_totals_by_project(organization_id, start_date, end_date)
        # Already sorted by total_cost desc from the repository
        return all_projects[:limit]
