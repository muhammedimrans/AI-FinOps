"""DashboardService — F-060 through F-066 (EP-10).

Thin orchestration layer that composes responses from existing analytics
services and repositories. Contains no business logic — all calculations
are delegated to AnalyticsService and repositories.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
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


def _period_over_period_pct(current: Decimal, prior: Decimal) -> Decimal | None:
    """Percent change of ``current`` vs. ``prior`` (EP-24.1).

    ``None`` when there is no prior-period baseline to compare against
    (division by zero) — the frontend renders that as "no trend data"
    rather than a misleading 0% or a fabricated 100%.
    """
    if prior == 0:
        return None
    return ((current - prior) / prior) * Decimal(100)


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
        """Compose executive dashboard summary from cost and collection data.

        EP-24.1 additions: ``active_projects`` (distinct projects with any
        spend, all time — reuses the already-fetched project breakdown
        rows rather than a second query), ``avg_cost_per_request``
        (division over the already-computed all-time totals — no new
        query), and period-over-period trend percentages for cost/
        requests/tokens (this period vs. the immediately preceding period
        of equal length, both derived from ``get_totals_by_org`` — the
        same aggregate this method already calls, just called twice more
        with shifted date ranges instead of adding a new repository
        method).
        """
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
        project_rows = await cost_repo.get_totals_by_project(
            organization_id,
            date(2000, 1, 1),
            today,
        )
        active_providers = len({r["provider"] for r in provider_rows})
        active_models = len({(r["provider"], r["model"]) for r in model_rows})
        active_projects = len(
            {r["project_id"] for r in project_rows if r["project_id"] is not None}
        )

        avg_cost_per_request: Decimal | None = None
        if total_requests > 0:
            avg_cost_per_request = total_cost / Decimal(total_requests)

        # Trailing 30-day period vs. the 30 days immediately before it —
        # a fixed, predictable window rather than one keyed off whatever
        # date range a caller happens to be viewing.
        period_end = today
        period_start = today - timedelta(days=29)
        prior_end = period_start - timedelta(days=1)
        prior_start = prior_end - timedelta(days=29)

        current_period_rows = await cost_repo.get_totals_by_org(
            organization_id, period_start, period_end
        )
        prior_period_rows = await cost_repo.get_totals_by_org(
            organization_id, prior_start, prior_end
        )

        current_cost = sum(r["total_cost"] for r in current_period_rows) or Decimal(0)
        current_tokens = sum(r["total_tokens"] for r in current_period_rows)
        current_requests = sum(r["record_count"] for r in current_period_rows)
        prior_cost = sum(r["total_cost"] for r in prior_period_rows) or Decimal(0)
        prior_tokens = sum(r["total_tokens"] for r in prior_period_rows)
        prior_requests = sum(r["record_count"] for r in prior_period_rows)

        cost_trend_pct = _period_over_period_pct(current_cost, prior_cost)
        request_trend_pct = _period_over_period_pct(
            Decimal(current_requests), Decimal(prior_requests)
        )
        token_trend_pct = _period_over_period_pct(Decimal(current_tokens), Decimal(prior_tokens))

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
            active_projects=active_projects,
        )

        return {
            "total_spend": total_cost,
            "today_spend": today_spend,
            "month_spend": month_spend,
            "total_tokens": total_tokens,
            "total_requests": total_requests,
            "active_providers": active_providers,
            "active_models": active_models,
            "active_projects": active_projects,
            "avg_cost_per_request": avg_cost_per_request,
            "cost_trend_pct": cost_trend_pct,
            "request_trend_pct": request_trend_pct,
            "token_trend_pct": token_trend_pct,
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
        *,
        project_id: uuid.UUID | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return time-bucketed cost data.

        Daily: raw rows from get_daily_trend.
        Weekly: grouped by ISO week in Python.
        Monthly: grouped by (year, month) in Python.

        EP-24.1: ``prompt_tokens``/``completion_tokens`` are carried
        through every bucket (Token Trend chart's input/output split),
        and optional ``project_id``/``provider``/``model`` filters narrow
        the underlying ``get_daily_trend`` query.
        """
        svc = self._make_analytics_service()
        daily_rows = await svc.get_daily_trend(
            organization_id,
            start_date,
            end_date,
            project_id=project_id,
            provider=provider,
            model=model,
        )

        if granularity == "daily":
            return [
                {
                    "date": r["usage_date"].isoformat(),
                    "cost": r["total_cost"],
                    "tokens": r["total_tokens"],
                    "prompt_tokens": r["total_prompt_tokens"],
                    "completion_tokens": r["total_completion_tokens"],
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
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "requests": 0,
                        "currency": r["currency"],
                    }
                buckets[key]["cost"] += r["total_cost"]
                buckets[key]["tokens"] += r["total_tokens"]
                buckets[key]["prompt_tokens"] += r["total_prompt_tokens"]
                buckets[key]["completion_tokens"] += r["total_completion_tokens"]
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
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "requests": 0,
                        "currency": r["currency"],
                    }
                mbuckets[key]["cost"] += r["total_cost"]
                mbuckets[key]["tokens"] += r["total_tokens"]
                mbuckets[key]["prompt_tokens"] += r["total_prompt_tokens"]
                mbuckets[key]["completion_tokens"] += r["total_completion_tokens"]
                mbuckets[key]["requests"] += r["record_count"]
            return list(mbuckets.values())

        # Unknown granularity falls back to daily
        log.warning("unknown_granularity", granularity=granularity)
        return [
            {
                "date": r["usage_date"].isoformat(),
                "cost": r["total_cost"],
                "tokens": r["total_tokens"],
                "prompt_tokens": r["total_prompt_tokens"],
                "completion_tokens": r["total_completion_tokens"],
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
        *,
        project_id: uuid.UUID | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> list[dict[str, Any]]:
        """Per-provider cost and token breakdown.

        EP-24.1: ``input_tokens``/``output_tokens`` and ``model_count``
        (distinct models seen for that provider, computed in SQL by
        ``get_totals_by_provider`` — see that method's docstring) are now
        real fields, closing the frontend's previous ``input_tokens: 0``/
        ``model_count: 0`` placeholders.
        """
        svc = self._make_analytics_service()
        rows = await svc.get_provider_breakdown(
            organization_id,
            start_date,
            end_date,
            project_id=project_id,
            provider=provider,
            model=model,
        )
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
                    "input_tokens": r["total_prompt_tokens"],
                    "output_tokens": r["total_completion_tokens"],
                    "model_count": r["model_count"],
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
        *,
        project_id: uuid.UUID | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> list[dict[str, Any]]:
        """Per-model cost and token breakdown, sorted by total_cost desc.

        EP-24.1: ``input_tokens``/``output_tokens`` are now real fields
        (previously ``input_tokens: 0``/``output_tokens`` proxied from
        ``total_tokens`` on the frontend).
        """
        svc = self._make_analytics_service()
        rows = await svc.get_top_models(
            organization_id,
            start_date,
            end_date,
            limit=limit,
            project_id=project_id,
            provider=provider,
            model=model,
        )
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
                    "input_tokens": r["total_prompt_tokens"],
                    "output_tokens": r["total_completion_tokens"],
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
        *,
        project_id: uuid.UUID | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> list[dict[str, Any]]:
        """Per-project cost and token breakdown.

        EP-24.1: joins ``Project`` (in Python, over the small already-
        grouped result set — not a second SQL join into the cost-record
        aggregate) to attach the real ``project_name`` and ``budget``,
        replacing the frontend's previous ``project_name: project_id``/
        ``budget: "0"`` placeholders. ``budget_utilization_pct`` is a
        division over fields already in hand, no new query.
        """
        from app.repositories.project_repository import ProjectRepository

        svc = self._make_analytics_service()
        rows = await svc.get_project_breakdown(
            organization_id,
            start_date,
            end_date,
            project_id=project_id,
            provider=provider,
            model=model,
        )

        project_repo = ProjectRepository(self._session)
        projects_page = await project_repo.list_by_org(organization_id, limit=500)
        projects_by_id = {p.id: p for p in projects_page.items}

        result = []
        for r in rows:
            pid = r["project_id"]
            project = projects_by_id.get(pid) if pid is not None else None
            total_cost = r["total_cost"] or Decimal(0)
            budget = project.budget if project is not None else None
            budget_utilization_pct: Decimal | None = None
            if budget is not None and budget > 0:
                budget_utilization_pct = (total_cost / budget) * Decimal(100)
            result.append(
                {
                    "project_id": str(pid) if pid is not None else None,
                    "project_name": project.name if project is not None else "Unassigned",
                    "total_cost": total_cost,
                    "total_tokens": r["total_tokens"],
                    "total_requests": r["record_count"],
                    "budget": budget,
                    "budget_utilization_pct": budget_utilization_pct,
                    "currency": r["currency"],
                }
            )
        return result

    # ── F-066 — KPIs ────────────────────────────────────────────────────────────

    async def get_kpis(
        self,
        organization_id: uuid.UUID,
        start_date: date,
        end_date: date,
        *,
        project_id: uuid.UUID | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Derive KPIs from cost data: highest-cost provider/model, avg costs."""
        svc = self._make_analytics_service()

        provider_rows = await svc.get_provider_breakdown(
            organization_id,
            start_date,
            end_date,
            project_id=project_id,
            provider=provider,
            model=model,
        )
        model_rows = await svc.get_model_breakdown(
            organization_id,
            start_date,
            end_date,
            project_id=project_id,
            provider=provider,
            model=model,
        )

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
        org_rows = await cost_repo.get_totals_by_org(
            organization_id,
            start_date,
            end_date,
            project_id=project_id,
            provider=provider,
            model=model,
        )
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

    # ── EP-24.1 — Usage heatmap ─────────────────────────────────────────────────

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
        """Cost-weighted hour-of-day x day-of-week grid.

        Thin pass-through to ``UsageCostRecordRepository.get_heatmap`` via
        ``AnalyticsService`` — no aggregation logic lives here, matching
        every other breakdown method in this class.
        """
        svc = self._make_analytics_service()
        rows = await svc.get_heatmap(
            organization_id,
            start_date,
            end_date,
            project_id=project_id,
            provider=provider,
            model=model,
        )
        return [
            {
                "hour_of_day": r["hour_of_day"],
                "day_of_week": r["day_of_week"],
                "total_cost": r["total_cost"],
                "total_tokens": r["total_tokens"],
                "total_requests": r["record_count"],
                "currency": r["currency"],
            }
            for r in rows
        ]

    # ── EP-24.1 — Recent activity ───────────────────────────────────────────────

    async def get_recent_activity(
        self,
        organization_id: uuid.UUID,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Latest imports/syncs (UsageCollectionRun) + latest provider failures.

        Composes two already-existing repositories — no new tables, no
        new persisted "activity log." ``imports``/``syncs`` are the same
        ``UsageCollectionRun`` rows the EP-23.3/EP-23.4 sync UI already
        reads, split by ``triggered_by`` (MANUAL/API -> import-like,
        SCHEDULED -> background sync) purely for presentation; ``failures``
        reuses EP-22's ``last_failure_at``/``last_error`` fields on
        ``ProviderConnection`` (no separate failure log).
        """
        from app.repositories.provider_connection_repository import (
            ProviderConnectionRepository,
        )

        run_repo = self._run_repo()
        runs_page = await run_repo.list_by_org(organization_id, limit=limit, order="desc")

        imports = []
        syncs = []
        for run in runs_page.items:
            item = {
                "id": str(run.id),
                "provider": run.provider,
                "status": run.status.value,
                "triggered_by": run.triggered_by.value,
                "started_at": run.started_at,
                "completed_at": run.completed_at,
                "events_collected": run.events_collected,
                "error_message": run.error_message,
            }
            if run.triggered_by.value == "scheduled":
                syncs.append(item)
            else:
                imports.append(item)

        connection_repo = ProviderConnectionRepository(self._session)
        failed_connections = await connection_repo.list_recent_failures(
            organization_id, limit=limit
        )
        failures = [
            {
                "connection_id": str(c.id),
                "provider_type": c.provider_type.value,
                "display_name": c.display_name,
                "last_error": c.last_error,
                "last_failure_at": c.last_failure_at,
                "consecutive_failure_count": c.consecutive_failure_count,
            }
            for c in failed_connections
        ]

        return {
            "imports": imports[:limit],
            "syncs": syncs[:limit],
            "failures": failures,
        }
