"""Dashboard API endpoints — EP-10 (F-060 through F-066).

Endpoints
---------
GET /dashboard/overview             — F-060 executive overview
GET /dashboard/time-series          — F-061 cost time series
GET /dashboard/providers            — F-062 provider cost breakdown
GET /dashboard/models               — F-063 model cost breakdown
GET /dashboard/organization         — F-064 composite organization dashboard
GET /dashboard/projects             — F-065 project cost breakdown
GET /dashboard/kpis                 — F-066 derived KPIs
GET /dashboard/heatmap              — EP-24.1 hour-of-day x day-of-week usage heatmap
GET /dashboard/activity             — EP-24.1 recent activity (imports/syncs/failures)

Authentication
--------------
All endpoints require a valid JWT AND verified membership of the requested
organization (OrgScopedMembership) — the organization_id query parameter is
never trusted without a membership check.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Annotated

import structlog
from fastapi import APIRouter, HTTPException, Query

from app.api.deps import DbDep
from app.api.v1.budgets import _to_status_summary as _budget_to_status_summary
from app.auth.dependencies import OrgScopedMembership
from app.budgets.service import BudgetEvaluationService
from app.dashboard.service import DashboardService
from app.models.alert import AlertSeverity, AlertStatus, AlertType
from app.models.budget import Budget, BudgetPeriod, BudgetScopeType
from app.repositories.alert_repository import AlertRepository
from app.schemas.budgets import BudgetSummaryResponse
from app.schemas.dashboard import (
    ActivityFailureItem,
    ActivityResponse,
    ActivityRunItem,
    HeatmapCell,
    HeatmapResponse,
    KPIResponse,
    ModelBreakdownResponse,
    ModelMetrics,
    OrganizationDashboardResponse,
    OrganizationModelItem,
    OrganizationOverviewBlock,
    OrganizationProjectItem,
    OrganizationProviderItem,
    OrganizationTrendPoint,
    OverviewResponse,
    ProjectBreakdownResponse,
    ProjectMetrics,
    ProviderBreakdownResponse,
    ProviderMetrics,
    TimeSeriesPoint,
    TimeSeriesResponse,
)

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# ── Granularity enum (RH-01) ──────────────────────────────────────────────────


class Granularity(enum.StrEnum):
    """Valid time-series granularity values.

    FastAPI will return HTTP 422 automatically for any value not in this enum.
    """

    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"


# ── F-060 Executive Overview ───────────────────────────────────────────────────


@router.get(
    "/overview",
    response_model=OverviewResponse,
    summary="Executive dashboard overview",
    description=(
        "Returns high-level spend metrics for an organization: total spend, "
        "today's spend, month-to-date spend, token and request counts, "
        "active provider/model counts, and latest collection run status."
    ),
)
async def get_overview(
    db: DbDep,
    _member: OrgScopedMembership,
    organization_id: Annotated[uuid.UUID, Query(description="Organization ID")],
    currency: Annotated[str, Query(description="Target currency")] = "USD",
) -> OverviewResponse:
    """Return executive dashboard overview for an organization."""
    svc = DashboardService(session=db)
    data = await svc.get_overview(organization_id)
    return OverviewResponse(
        total_spend=str(data["total_spend"]),
        today_spend=str(data["today_spend"]),
        month_spend=str(data["month_spend"]),
        total_tokens=data["total_tokens"],
        total_requests=data["total_requests"],
        active_providers=data["active_providers"],
        active_models=data["active_models"],
        active_projects=data["active_projects"],
        avg_cost_per_request=str(data["avg_cost_per_request"] or 0),
        cost_trend_pct=(
            str(data["cost_trend_pct"]) if data["cost_trend_pct"] is not None else None
        ),
        request_trend_pct=(
            str(data["request_trend_pct"]) if data["request_trend_pct"] is not None else None
        ),
        token_trend_pct=(
            str(data["token_trend_pct"]) if data["token_trend_pct"] is not None else None
        ),
        collection_status=data["collection_status"],
        last_collection_at=data["last_collection_at"],
        currency=currency,
    )


# ── F-061 Time Series ──────────────────────────────────────────────────────────


@router.get(
    "/time-series",
    response_model=TimeSeriesResponse,
    summary="Cost time series",
    description=(
        "Returns cost data bucketed by the requested granularity: "
        "'daily', 'weekly' (ISO weeks), or 'monthly'."
    ),
)
async def get_time_series(
    db: DbDep,
    _member: OrgScopedMembership,
    organization_id: Annotated[uuid.UUID, Query(description="Organization ID")],
    start_date: Annotated[date, Query(description="Start date (inclusive)")],
    end_date: Annotated[date, Query(description="End date (inclusive)")],
    granularity: Annotated[
        Granularity,
        Query(description="Bucket size: daily, weekly, monthly"),
    ] = Granularity.daily,
    currency: Annotated[str, Query(description="Target currency")] = "USD",
    project_id: Annotated[uuid.UUID | None, Query(description="Filter to one project")] = None,
    provider: Annotated[str | None, Query(description="Filter to one provider")] = None,
    model: Annotated[str | None, Query(description="Filter to one model")] = None,
) -> TimeSeriesResponse:
    """Return time-bucketed cost data for an organization."""
    # RH-01: granularity validated by enum above (FastAPI returns 422 for invalid values)
    # RH-02: date range validation
    if start_date > end_date:
        raise HTTPException(
            status_code=422,
            detail="start_date must be before or equal to end_date",
        )
    svc = DashboardService(session=db)
    points_data = await svc.get_time_series(
        organization_id,
        start_date,
        end_date,
        granularity=granularity.value,
        project_id=project_id,
        provider=provider,
        model=model,
    )
    # RH-02: filter to requested currency before summing
    filtered = [p for p in points_data if p.get("currency", currency) == currency]
    points = [
        TimeSeriesPoint(
            date=p["date"],
            cost=str(p["cost"]),
            tokens=p["tokens"],
            prompt_tokens=p["prompt_tokens"],
            completion_tokens=p["completion_tokens"],
            requests=p["requests"],
            currency=p.get("currency", currency),
        )
        for p in filtered
    ]
    total_cost = sum((p["cost"] for p in filtered), Decimal(0))
    total_tokens = sum(p["tokens"] for p in filtered)
    total_requests = sum(p["requests"] for p in filtered)
    return TimeSeriesResponse(
        granularity=granularity.value,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        points=points,
        total_cost=str(total_cost),
        total_tokens=total_tokens,
        total_requests=total_requests,
    )


# ── F-062 Provider Analytics ───────────────────────────────────────────────────


@router.get(
    "/providers",
    response_model=ProviderBreakdownResponse,
    summary="Provider cost breakdown",
    description="Returns cost and usage metrics grouped by AI provider.",
)
async def get_provider_breakdown(
    db: DbDep,
    _member: OrgScopedMembership,
    organization_id: Annotated[uuid.UUID, Query(description="Organization ID")],
    start_date: Annotated[date, Query(description="Start date (inclusive)")],
    end_date: Annotated[date, Query(description="End date (inclusive)")],
    currency: Annotated[str, Query(description="Target currency")] = "USD",
    project_id: Annotated[uuid.UUID | None, Query(description="Filter to one project")] = None,
    provider: Annotated[str | None, Query(description="Filter to one provider")] = None,
    model: Annotated[str | None, Query(description="Filter to one model")] = None,
) -> ProviderBreakdownResponse:
    """Return provider-level cost breakdown."""
    # RH-02: date range validation
    if start_date > end_date:
        raise HTTPException(
            status_code=422,
            detail="start_date must be before or equal to end_date",
        )
    svc = DashboardService(session=db)
    rows = await svc.get_provider_breakdown(
        organization_id,
        start_date,
        end_date,
        project_id=project_id,
        provider=provider,
        model=model,
    )
    # RH-02 (currency safety): filter to requested currency before summing
    filtered = [r for r in rows if r.get("currency", currency) == currency]
    providers = [
        ProviderMetrics(
            provider=r["provider"],
            total_cost=str(r["total_cost"]),
            total_tokens=r["total_tokens"],
            input_tokens=r["input_tokens"],
            output_tokens=r["output_tokens"],
            model_count=r["model_count"],
            total_requests=r["total_requests"],
            avg_cost_per_request=str(r["avg_cost_per_request"]),
            currency=r.get("currency", currency),
        )
        for r in filtered
    ]
    total_cost = sum((r["total_cost"] for r in filtered), Decimal(0))
    return ProviderBreakdownResponse(
        providers=providers,
        total_cost=str(total_cost),
        period_start=start_date.isoformat(),
        period_end=end_date.isoformat(),
    )


# ── F-063 Model Analytics ──────────────────────────────────────────────────────


@router.get(
    "/models",
    response_model=ModelBreakdownResponse,
    summary="Model cost breakdown",
    description="Returns cost and usage metrics grouped by model, sorted by cost descending.",
)
async def get_model_breakdown(
    db: DbDep,
    _member: OrgScopedMembership,
    organization_id: Annotated[uuid.UUID, Query(description="Organization ID")],
    start_date: Annotated[date, Query(description="Start date (inclusive)")],
    end_date: Annotated[date, Query(description="End date (inclusive)")],
    limit: Annotated[int, Query(description="Maximum models to return", ge=1, le=100)] = 20,
    currency: Annotated[str, Query(description="Target currency")] = "USD",
    project_id: Annotated[uuid.UUID | None, Query(description="Filter to one project")] = None,
    provider: Annotated[str | None, Query(description="Filter to one provider")] = None,
    model: Annotated[str | None, Query(description="Filter to one model")] = None,
) -> ModelBreakdownResponse:
    """Return model-level cost breakdown."""
    # RH-02: date range validation
    if start_date > end_date:
        raise HTTPException(
            status_code=422,
            detail="start_date must be before or equal to end_date",
        )
    svc = DashboardService(session=db)
    rows = await svc.get_model_breakdown(
        organization_id,
        start_date,
        end_date,
        limit=limit,
        project_id=project_id,
        provider=provider,
        model=model,
    )
    # RH-02 (currency safety): filter to requested currency before summing
    filtered = [r for r in rows if r.get("currency", currency) == currency]
    models = [
        ModelMetrics(
            provider=r["provider"],
            model=r["model"],
            total_cost=str(r["total_cost"]),
            total_tokens=r["total_tokens"],
            input_tokens=r["input_tokens"],
            output_tokens=r["output_tokens"],
            total_requests=r["total_requests"],
            avg_cost_per_request=str(r["avg_cost_per_request"]),
            currency=r.get("currency", currency),
        )
        for r in filtered
    ]
    total_cost = sum((r["total_cost"] for r in filtered), Decimal(0))
    return ModelBreakdownResponse(
        models=models,
        total_cost=str(total_cost),
        period_start=start_date.isoformat(),
        period_end=end_date.isoformat(),
    )


# ── F-064 Organization Dashboard ──────────────────────────────────────────────


@router.get(
    "/organization",
    response_model=OrganizationDashboardResponse,
    summary="Composite organization dashboard",
    description=(
        "Returns a combined response with overview metrics, provider breakdown, "
        "top 5 models, project breakdown, and daily cost trend (last 30 days)."
    ),
)
async def get_organization_dashboard(
    db: DbDep,
    _member: OrgScopedMembership,
    organization_id: Annotated[uuid.UUID, Query(description="Organization ID")],
    start_date: Annotated[
        date | None, Query(description="Start date (defaults to first of current month)")
    ] = None,
    end_date: Annotated[date | None, Query(description="End date (defaults to today)")] = None,
    currency: Annotated[str, Query(description="Target currency")] = "USD",
) -> OrganizationDashboardResponse:
    """Return composite organization dashboard."""
    today = datetime.now(tz=UTC).date()
    effective_end = end_date or today
    effective_start = start_date or effective_end.replace(day=1)

    # RH-02: date range validation (only when both are explicitly provided)
    if start_date is not None and end_date is not None and start_date > end_date:
        raise HTTPException(
            status_code=422,
            detail="start_date must be before or equal to end_date",
        )

    svc = DashboardService(session=db)

    # Sequential queries intentional: all calls share the same AsyncSession.
    # asyncio.gather() with a shared session is not safe with SQLAlchemy async.
    # Parallel execution would require per-call sessions — deferred to EP-11 optimization.
    overview_data = await svc.get_overview(organization_id, today=today)
    provider_rows = await svc.get_provider_breakdown(
        organization_id, effective_start, effective_end
    )
    model_rows = await svc.get_model_breakdown(
        organization_id, effective_start, effective_end, limit=5
    )
    project_rows = await svc.get_project_breakdown(organization_id, effective_start, effective_end)

    trend_start = today - timedelta(days=29)
    trend_rows = await svc.get_time_series(organization_id, trend_start, today, granularity="daily")

    # Currency filtering for breakdown sections
    filtered_providers = [r for r in provider_rows if r.get("currency", currency) == currency]
    filtered_models = [r for r in model_rows if r.get("currency", currency) == currency]
    filtered_projects = [r for r in project_rows if r.get("currency", currency) == currency]
    filtered_trend = [p for p in trend_rows if p.get("currency", currency) == currency]

    return OrganizationDashboardResponse(
        organization_id=str(organization_id),
        period_start=effective_start.isoformat(),
        period_end=effective_end.isoformat(),
        currency=currency,
        overview=OrganizationOverviewBlock(
            total_spend=str(overview_data["total_spend"]),
            today_spend=str(overview_data["today_spend"]),
            month_spend=str(overview_data["month_spend"]),
            total_tokens=overview_data["total_tokens"],
            total_requests=overview_data["total_requests"],
            active_providers=overview_data["active_providers"],
            active_models=overview_data["active_models"],
            collection_status=overview_data["collection_status"],
            last_collection_at=(
                overview_data["last_collection_at"].isoformat()
                if overview_data["last_collection_at"]
                else None
            ),
        ),
        provider_breakdown=[
            OrganizationProviderItem(
                provider=r["provider"],
                total_cost=str(r["total_cost"]),
                total_tokens=r["total_tokens"],
                total_requests=r["total_requests"],
                avg_cost_per_request=str(r["avg_cost_per_request"]),
                currency=r.get("currency", currency),
            )
            for r in filtered_providers
        ],
        top_models=[
            OrganizationModelItem(
                provider=r["provider"],
                model=r["model"],
                total_cost=str(r["total_cost"]),
                total_tokens=r["total_tokens"],
                total_requests=r["total_requests"],
                avg_cost_per_request=str(r["avg_cost_per_request"]),
                currency=r.get("currency", currency),
            )
            for r in filtered_models
        ],
        project_breakdown=[
            OrganizationProjectItem(
                project_id=r["project_id"],
                total_cost=str(r["total_cost"]),
                total_tokens=r["total_tokens"],
                total_requests=r["total_requests"],
                currency=r.get("currency", currency),
            )
            for r in filtered_projects
        ],
        daily_trend=[
            OrganizationTrendPoint(
                date=p["date"],
                cost=str(p["cost"]),
                tokens=p["tokens"],
                requests=p["requests"],
                currency=p.get("currency", currency),
            )
            for p in filtered_trend
        ],
    )


# ── F-065 Project Dashboard ───────────────────────────────────────────────────


@router.get(
    "/projects",
    response_model=ProjectBreakdownResponse,
    summary="Project cost breakdown",
    description="Returns cost and usage metrics grouped by project.",
)
async def get_project_breakdown(
    db: DbDep,
    _member: OrgScopedMembership,
    organization_id: Annotated[uuid.UUID, Query(description="Organization ID")],
    start_date: Annotated[date, Query(description="Start date (inclusive)")],
    end_date: Annotated[date, Query(description="End date (inclusive)")],
    currency: Annotated[str, Query(description="Target currency")] = "USD",
    project_id: Annotated[uuid.UUID | None, Query(description="Filter to one project")] = None,
    provider: Annotated[str | None, Query(description="Filter to one provider")] = None,
    model: Annotated[str | None, Query(description="Filter to one model")] = None,
) -> ProjectBreakdownResponse:
    """Return project-level cost breakdown."""
    # RH-02: date range validation
    if start_date > end_date:
        raise HTTPException(
            status_code=422,
            detail="start_date must be before or equal to end_date",
        )
    svc = DashboardService(session=db)
    rows = await svc.get_project_breakdown(
        organization_id,
        start_date,
        end_date,
        project_id=project_id,
        provider=provider,
        model=model,
    )
    # RH-02 (currency safety): filter to requested currency before summing
    filtered = [r for r in rows if r.get("currency", currency) == currency]
    projects = [
        ProjectMetrics(
            project_id=r["project_id"],
            project_name=r["project_name"],
            total_cost=str(r["total_cost"]),
            total_tokens=r["total_tokens"],
            total_requests=r["total_requests"],
            budget=str(r["budget"]) if r["budget"] is not None else None,
            budget_utilization_pct=(
                str(r["budget_utilization_pct"])
                if r["budget_utilization_pct"] is not None
                else None
            ),
            currency=r.get("currency", currency),
        )
        for r in filtered
    ]
    total_cost = sum((r["total_cost"] for r in filtered), Decimal(0))
    return ProjectBreakdownResponse(
        projects=projects,
        total_cost=str(total_cost),
        period_start=start_date.isoformat(),
        period_end=end_date.isoformat(),
    )


# ── F-066 KPIs ─────────────────────────────────────────────────────────────────


@router.get(
    "/kpis",
    response_model=KPIResponse,
    summary="Derived KPIs",
    description=(
        "Returns derived key performance indicators: highest-cost provider and model, "
        "average cost per request and per token."
    ),
)
async def get_kpis(
    db: DbDep,
    _member: OrgScopedMembership,
    organization_id: Annotated[uuid.UUID, Query(description="Organization ID")],
    start_date: Annotated[date, Query(description="Start date (inclusive)")],
    end_date: Annotated[date, Query(description="End date (inclusive)")],
    currency: Annotated[str, Query(description="Target currency")] = "USD",
    project_id: Annotated[uuid.UUID | None, Query(description="Filter to one project")] = None,
    provider: Annotated[str | None, Query(description="Filter to one provider")] = None,
    model: Annotated[str | None, Query(description="Filter to one model")] = None,
) -> KPIResponse:
    """Return derived KPIs for an organization."""
    # RH-02: date range validation
    if start_date > end_date:
        raise HTTPException(
            status_code=422,
            detail="start_date must be before or equal to end_date",
        )
    svc = DashboardService(session=db)
    data = await svc.get_kpis(
        organization_id, start_date, end_date, project_id=project_id, provider=provider, model=model
    )
    return KPIResponse(
        highest_cost_provider=data["highest_cost_provider"],
        highest_cost_model=data["highest_cost_model"],
        avg_cost_per_request=(
            str(data["avg_cost_per_request"]) if data["avg_cost_per_request"] is not None else None
        ),
        avg_cost_per_token=(
            str(data["avg_cost_per_token"]) if data["avg_cost_per_token"] is not None else None
        ),
        period_start=start_date.isoformat(),
        period_end=end_date.isoformat(),
        currency=currency,
    )


# ── EP-24.1 Usage Heatmap ────────────────────────────────────────────────────


@router.get(
    "/heatmap",
    response_model=HeatmapResponse,
    summary="Usage heatmap (hour-of-day x day-of-week)",
    description=(
        "Returns a cost-weighted grid of hour-of-day (0-23, UTC) x day-of-week "
        "(0=Sunday..6=Saturday) usage, for the Usage Heatmap chart."
    ),
)
async def get_heatmap(
    db: DbDep,
    _member: OrgScopedMembership,
    organization_id: Annotated[uuid.UUID, Query(description="Organization ID")],
    start_date: Annotated[date, Query(description="Start date (inclusive)")],
    end_date: Annotated[date, Query(description="End date (inclusive)")],
    currency: Annotated[str, Query(description="Target currency")] = "USD",
    project_id: Annotated[uuid.UUID | None, Query(description="Filter to one project")] = None,
    provider: Annotated[str | None, Query(description="Filter to one provider")] = None,
    model: Annotated[str | None, Query(description="Filter to one model")] = None,
) -> HeatmapResponse:
    """Return the hour-of-day x day-of-week usage heatmap."""
    # RH-02: date range validation
    if start_date > end_date:
        raise HTTPException(
            status_code=422,
            detail="start_date must be before or equal to end_date",
        )
    svc = DashboardService(session=db)
    rows = await svc.get_heatmap(
        organization_id,
        start_date,
        end_date,
        project_id=project_id,
        provider=provider,
        model=model,
    )
    # RH-02 (currency safety): filter to requested currency
    filtered = [r for r in rows if r.get("currency", currency) == currency]
    cells = [
        HeatmapCell(
            hour_of_day=r["hour_of_day"],
            day_of_week=r["day_of_week"],
            total_cost=str(r["total_cost"]),
            total_tokens=r["total_tokens"],
            total_requests=r["total_requests"],
            currency=r.get("currency", currency),
        )
        for r in filtered
    ]
    return HeatmapResponse(
        cells=cells,
        period_start=start_date.isoformat(),
        period_end=end_date.isoformat(),
        currency=currency,
    )


# ── EP-24.1 Recent Activity ──────────────────────────────────────────────────


@router.get(
    "/activity",
    response_model=ActivityResponse,
    summary="Recent activity feed",
    description=(
        "Returns the latest usage-collection imports, the latest background "
        "syncs, and any provider connections currently in a failed state."
    ),
)
async def get_activity(
    db: DbDep,
    _member: OrgScopedMembership,
    organization_id: Annotated[uuid.UUID, Query(description="Organization ID")],
    limit: Annotated[int, Query(description="Maximum items per section", ge=1, le=100)] = 20,
) -> ActivityResponse:
    """Return the recent activity feed for an organization."""
    svc = DashboardService(session=db)
    data = await svc.get_recent_activity(organization_id, limit=limit)
    return ActivityResponse(
        imports=[ActivityRunItem(**item) for item in data["imports"]],
        syncs=[ActivityRunItem(**item) for item in data["syncs"]],
        failures=[ActivityFailureItem(**item) for item in data["failures"]],
    )


# ── EP-24.2 Budget Summary ───────────────────────────────────────────────────


@router.get(
    "/budget-summary",
    response_model=BudgetSummaryResponse,
    summary="Budget status summary — for the Budgets page and the Overview KPI cards",
    description=(
        "Every enabled budget's current spend/remaining/forecast/status (EP-24.2), "
        "plus the organization-wide 'Budget Remaining' / 'Active Alerts' / "
        "'Critical Alerts' / 'Projected End-of-Month Spend' figures the Overview "
        "page's KPI cards need. Read-only — never fires alerts (that only happens "
        "via BudgetEvaluationService.evaluate_and_alert(), called after a usage "
        "sync — see app/services/usage_sync_scheduler.py and "
        "app/api/v1/provider_connections.py)."
    ),
)
async def get_budget_summary(
    db: DbDep,
    _member: OrgScopedMembership,
    organization_id: Annotated[uuid.UUID, Query(description="Organization ID")],
    currency: Annotated[str, Query(description="Target currency")] = "USD",
) -> BudgetSummaryResponse:
    evaluator = BudgetEvaluationService(db)  # read-only — no alert_service
    evaluations = await evaluator.evaluate_organization(organization_id)
    summaries = [_budget_to_status_summary(e) for e in evaluations if e.budget.currency == currency]

    total_budgeted = sum(
        (e.budget.amount for e in evaluations if e.budget.currency == currency), Decimal(0)
    )
    total_spent = sum(
        (e.current_spend for e in evaluations if e.budget.currency == currency), Decimal(0)
    )
    total_remaining = total_budgeted - total_spent

    alert_repo = AlertRepository(db)
    budget_alerts = []
    for alert_type in (AlertType.BUDGET_THRESHOLD, AlertType.BUDGET_EXCEEDED):
        budget_alerts.extend(
            await alert_repo.list_for_org(
                organization_id, status=AlertStatus.OPEN, alert_type=alert_type, limit=200
            )
        )
    active_alert_count = len(budget_alerts)
    critical_alert_count = sum(
        1 for a in budget_alerts if a.severity in (AlertSeverity.HIGH, AlertSeverity.CRITICAL)
    )

    # Organization-wide monthly spend projection, independent of any
    # configured Budget row — reuses the exact same evaluation machinery
    # (resolve_period_window + UsageCostRecordRepository.get_totals_by_org
    # via BudgetEvaluationService.evaluate_budget) against an in-memory,
    # never-persisted "virtual" organization-scoped monthly budget. No
    # second forecast formula, no second aggregation query.
    virtual_budget = Budget(
        organization_id=organization_id,
        name="__organization_projection__",
        scope_type=BudgetScopeType.ORGANIZATION,
        amount=Decimal(1),
        currency=currency,
        period=BudgetPeriod.MONTHLY,
        threshold_percentages=[100.0],
    )
    projection = await evaluator.evaluate_budget(virtual_budget)

    return BudgetSummaryResponse(
        budgets=summaries,
        currency=currency,
        total_budgeted=str(total_budgeted),
        total_spent=str(total_spent),
        total_remaining=str(total_remaining),
        active_alert_count=active_alert_count,
        critical_alert_count=critical_alert_count,
        projected_eom_spend=str(projection.projected_period_spend),
    )
