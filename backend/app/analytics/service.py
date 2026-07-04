"""AnalyticsService — F-053 (EP-09).

Read-only analytics over cost records and daily summaries.
Provides breakdowns by provider, model, project, and date.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any

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
    ) -> dict[str, Any]:
        """Total tokens, requests, events for org in date range.

        Token counts are currency-agnostic (tokens are not monetary), so we
        sum across all currencies returned by get_totals_by_org().
        """
        rows = await self._cost_repo.get_totals_by_org(organization_id, start_date, end_date)
        total_tokens = sum(r["total_tokens"] for r in rows)
        total_prompt_tokens = sum(r["total_prompt_tokens"] for r in rows)
        total_completion_tokens = sum(r["total_completion_tokens"] for r in rows)
        record_count = sum(r["record_count"] for r in rows)
        return {
            "organization_id": str(organization_id),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "total_tokens": total_tokens,
            "total_prompt_tokens": total_prompt_tokens,
            "total_completion_tokens": total_completion_tokens,
            "total_requests": record_count,
            "event_count": record_count,
        }

    async def get_cost_summary(
        self,
        organization_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> dict[str, Any]:
        """Total costs by currency for org in date range.

        Returns a list of per-currency totals so that USD and EUR costs are
        never summed together. Callers should present each currency separately.
        """
        rows = await self._cost_repo.get_totals_by_org(organization_id, start_date, end_date)
        return {
            "organization_id": str(organization_id),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "cost_by_currency": [
                {
                    "currency": r["currency"],
                    "total_cost": r["total_cost"],
                    "total_tokens": r["total_tokens"],
                    "record_count": r["record_count"],
                }
                for r in rows
            ],
            # Convenience fields for single-currency deployments (first currency or zero)
            "total_cost": rows[0]["total_cost"] if rows else Decimal(0),
            "total_tokens": sum(r["total_tokens"] for r in rows),
            "record_count": sum(r["record_count"] for r in rows),
        }

    async def get_provider_breakdown(
        self,
        organization_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        """Per-provider cost and token breakdown."""
        return await self._cost_repo.get_totals_by_provider(organization_id, start_date, end_date)

    async def get_model_breakdown(
        self,
        organization_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        """Per-model cost and token breakdown."""
        return await self._cost_repo.get_totals_by_model(organization_id, start_date, end_date)

    async def get_project_breakdown(
        self,
        organization_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        """Per-project cost and token breakdown."""
        return await self._cost_repo.get_totals_by_project(organization_id, start_date, end_date)

    async def get_daily_trend(
        self,
        organization_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        """Day-by-day cost totals ordered by date."""
        return await self._cost_repo.get_daily_trend(organization_id, start_date, end_date)

    async def get_top_models(
        self,
        organization_id: uuid.UUID,
        start_date: date,
        end_date: date,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Top N models by total cost. SQL LIMIT applied in the repository."""
        return await self._cost_repo.get_totals_by_model(
            organization_id, start_date, end_date, limit=limit
        )

    async def get_top_projects(
        self,
        organization_id: uuid.UUID,
        start_date: date,
        end_date: date,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Top N projects by total cost. SQL LIMIT applied in the repository."""
        return await self._cost_repo.get_totals_by_project(
            organization_id, start_date, end_date, limit=limit
        )
