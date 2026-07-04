"""DashboardService — F-060 through F-066 (EP-10).

Thin orchestration layer that composes responses from existing analytics
services and repositories. Contains no business logic — all calculations
are delegated to AnalyticsService and repositories.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from app.analytics.service import AnalyticsService
    from app.repositories.usage_collection_run_repository import (
        UsageCollectionRunRepository,
    )
    from app.repositories.usage_cost_record_repository import UsageCostRecordRepository

log = structlog.get_logger(__name__)

_DEFAULT_CURRENCY = "USD"


class DashboardService:
    """Orchestration layer for executive dashboard endpoints.

    All heavy-lifting (aggregation queries, cost breakdowns, trend data)
    is delegated to UsageCostRecordRepository via AnalyticsService.
    This class only composes responses — no SQL is written here.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Internal helpers ────────────────────────────────────────────────────────

    def _make_analytics_service(self) -> AnalyticsService:
        from app.analytics.service import AnalyticsService
        from app.repositories.daily_cost_summary_repository import DailyCostSummaryRepository
        from app.repositories.usage_cost_record_repository import UsageCostRecordRepository

        return AnalyticsService(
            cost_record_repo=UsageCostRecordRepository(self._session),
            daily_summary_repo=DailyCostSummaryRepository(self._session),
        )

    def _cost_repo(self) -> UsageCostRecordRepository:
        from app.repositories.usage_cost_record_repository import UsageCostRecordRepository

        return UsageCostRecordRepository(self._session)

    def _run_repo(self) -> UsageCollectionRunRepository:
        from app.repositories.usage_collection_run_repository import UsageCollectionRunRepository

        return UsageCollectionRunRepository(self._session)

    # ── F-060 — Executive overview ──────────────────────────────────────────────

    async def get_overview(
        self,
        organization_id: uuid.UUID,
        today: date | None = None,
    ) -> dict[str, Any]:
        """Compose executive dashboard summary from cost and collection data."""
        if today is None:
            today = datetime.now(tz=UTC).date()

        month_start = today.replace(day=1)

        cost_repo = self._cost_repo()

        # Total spend (all time)
        all_time_rows = await cost_repo.get_totals_by_org(
            organization_id,
            date(2000, 1, 1),
            today,
        )
        total_cost = sum(r["total_cost"] for r in all_time_rows) or Decimal(0)
        total_tokens = sum(r["total_tokens"] for r in all_time_rows)
        total_requests = sum(r["record_count"] for r in all_time_rows)

        # Month-to-date spend
        month_rows = await cost_repo.get_totals_by_org(
            organization_id,
            month_start,
            today,
        )
        month_spend = sum(r["total_cost"] for r in month_rows) or Decimal(0)

        # Today's spend
        today_rows = await cost_repo.get_totals_by_org(
            organization_id,
            today,
            today,
        )
        today_spend = sum(r["total_cost"] for r in today_rows) or Decimal(0)

        # Active providers and models
        provider_rows = await cost_repo.get_totals_by_provider(
            organization_id,
            date(2000, 1, 1),
            today,
        )
        model_rows = await cost_repo.get_totals_by_model(
            organization_id,
            date(2000, 1, 1),
            today,
        )
        active_providers = len({r["provider"] for r in provider_rows})
        active_models = len({(r["provider"], r["model"]) for r in model_rows})

        # Latest collection run
        from app.models.usage_collection_run import UsageCollectionRun

        stmt = (
            select(UsageCollectionRun)
            .where(
                and_(
                    UsageCollectionRun.organization_id == organization_id,
                    UsageCollectionRun.deleted_at.is_(None),
                )
            )
            .order_by(desc(UsageCollectionRun.started_at))
            .limit(1)
        )
        result = await self._session.execute(stmt)
        latest_run = result.scalar_one_or_none()

        collection_status = latest_run.status.value if latest_run else None
        last_collection_at = latest_run.started_at if latest_run else None

        log.info(
            "dashboard_overview",
            organization_id=str(organization_id),
            total_cost=str(total_cost),
            active_providers=active_providers,
            active_models=active_models,
        )

        return {
            "total_spend": total_cost,
            "today_spend": today_spend,
            "month_spend": month_spend,
            "total_tokens": total_tokens,
            "total_requests": total_requests,
            "active_providers": active_providers,
            "active_models": active_models,
            "collection_status": collection_status,
            "last_collection_at": last_collection_at,
            "currency": _DEFAULT_CURRENCY,
        }

    # ── F-061 — Time series ─────────────────────────────────────────────────────

    async def get_time_series(
        self,
        organization_id: uuid.UUID,
        start_date: date,
        end_date: date,
        granularity: str = "daily",
    ) -> list[dict[str, Any]]:
        """Return time-bucketed cost data.

        Daily: raw rows from get_daily_trend.
        Weekly: grouped by ISO week in Python.
        Monthly: grouped by (year, month) in Python.
        """
        svc = self._make_analytics_service()
        daily_rows = await svc.get_daily_trend(organization_id, start_date, end_date)

        if granularity == "daily":
            return [
                {
                    "date": r["usage_date"].isoformat(),
                    "cost": r["total_cost"],
                    "tokens": r["total_tokens"],
                    "requests": r["record_count"],
                    "currency": r["currency"],
                }
                for r in daily_rows
            ]

        if granularity == "weekly":
            buckets: dict[str, dict[str, Any]] = {}
            for r in daily_rows:
                iso = r["usage_date"].isocalendar()
                key = f"{iso.year}-W{iso.week:02d}"
                if key not in buckets:
                    buckets[key] = {
                        "date": key,
                        "cost": Decimal(0),
                        "tokens": 0,
                        "requests": 0,
                        "currency": r["currency"],
                    }
                buckets[key]["cost"] += r["total_cost"]
                buckets[key]["tokens"] += r["total_tokens"]
                buckets[key]["requests"] += r["record_count"]
            return list(buckets.values())

        if granularity == "monthly":
            mbuckets: dict[str, dict[str, Any]] = {}
            for r in daily_rows:
                d = r["usage_date"]
                key = f"{d.year}-{d.month:02d}"
                if key not in mbuckets:
                    mbuckets[key] = {
                        "date": key,
                        "cost": Decimal(0),
                        "tokens": 0,
                        "requests": 0,
                        "currency": r["currency"],
                    }
                mbuckets[key]["cost"] += r["total_cost"]
                mbuckets[key]["tokens"] += r["total_tokens"]
                mbuckets[key]["requests"] += r["record_count"]
            return list(mbuckets.values())

        # Unknown granularity falls back to daily
        log.warning("unknown_granularity", granularity=granularity)
        return [
            {
                "date": r["usage_date"].isoformat(),
                "cost": r["total_cost"],
                "tokens": r["total_tokens"],
                "requests": r["record_count"],
                "currency": r["currency"],
            }
            for r in daily_rows
        ]

    # ── F-062 — Provider breakdown ──────────────────────────────────────────────

    async def get_provider_breakdown(
        self,
        organization_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        """Per-provider cost and token breakdown."""
        svc = self._make_analytics_service()
        rows = await svc.get_provider_breakdown(organization_id, start_date, end_date)
        result = []
        for r in rows:
            record_count = r["record_count"] or 0
            total_cost = r["total_cost"] or Decimal(0)
            avg_cost = (total_cost / record_count) if record_count > 0 else Decimal(0)
            result.append(
                {
                    "provider": r["provider"],
                    "total_cost": total_cost,
                    "total_tokens": r["total_tokens"],
                    "total_requests": record_count,
                    "avg_cost_per_request": avg_cost,
                    "currency": r["currency"],
                }
            )
        return result

    # ── F-063 — Model breakdown ─────────────────────────────────────────────────

    async def get_model_breakdown(
        self,
        organization_id: uuid.UUID,
        start_date: date,
        end_date: date,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Per-model cost and token breakdown, sorted by total_cost desc."""
        svc = self._make_analytics_service()
        rows = await svc.get_top_models(organization_id, start_date, end_date, limit=limit)
        result = []
        for r in rows:
            record_count = r["record_count"] or 0
            total_cost = r["total_cost"] or Decimal(0)
            avg_cost = (total_cost / record_count) if record_count > 0 else Decimal(0)
            result.append(
                {
                    "provider": r["provider"],
                    "model": r["model"],
                    "total_cost": total_cost,
                    "total_tokens": r["total_tokens"],
                    "total_requests": record_count,
                    "avg_cost_per_request": avg_cost,
                    "currency": r["currency"],
                }
            )
        return result

    # ── F-065 — Project breakdown ───────────────────────────────────────────────

    async def get_project_breakdown(
        self,
        organization_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        """Per-project cost and token breakdown."""
        svc = self._make_analytics_service()
        rows = await svc.get_project_breakdown(organization_id, start_date, end_date)
        return [
            {
                "project_id": str(r["project_id"]) if r["project_id"] is not None else None,
                "total_cost": r["total_cost"] or Decimal(0),
                "total_tokens": r["total_tokens"],
                "total_requests": r["record_count"],
                "currency": r["currency"],
            }
            for r in rows
        ]

    # ── F-066 — KPIs ────────────────────────────────────────────────────────────

    async def get_kpis(
        self,
        organization_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> dict[str, Any]:
        """Derive KPIs from cost data: highest-cost provider/model, avg costs."""
        svc = self._make_analytics_service()

        provider_rows = await svc.get_provider_breakdown(organization_id, start_date, end_date)
        model_rows = await svc.get_model_breakdown(organization_id, start_date, end_date)

        # Highest-cost provider
        highest_cost_provider: str | None = None
        if provider_rows:
            top = max(provider_rows, key=lambda r: r["total_cost"])
            highest_cost_provider = top["provider"]

        # Highest-cost model
        highest_cost_model: str | None = None
        if model_rows:
            top_model = max(model_rows, key=lambda r: r["total_cost"])
            highest_cost_model = top_model["model"]

        # Org-level totals for avg calculations
        cost_repo = self._cost_repo()
        org_rows = await cost_repo.get_totals_by_org(organization_id, start_date, end_date)
        total_cost = sum(r["total_cost"] for r in org_rows) or Decimal(0)
        total_tokens = sum(r["total_tokens"] for r in org_rows)
        total_requests = sum(r["record_count"] for r in org_rows)

        avg_cost_per_request: Decimal | None = None
        if total_requests > 0:
            avg_cost_per_request = total_cost / Decimal(total_requests)

        avg_cost_per_token: Decimal | None = None
        if total_tokens > 0:
            avg_cost_per_token = total_cost / Decimal(total_tokens)

        return {
            "highest_cost_provider": highest_cost_provider,
            "highest_cost_model": highest_cost_model,
            "avg_cost_per_request": avg_cost_per_request,
            "avg_cost_per_token": avg_cost_per_token,
            "currency": _DEFAULT_CURRENCY,
        }
