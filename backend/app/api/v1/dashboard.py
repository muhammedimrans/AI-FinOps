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

Authentication
--------------
All endpoints require a valid JWT (CurrentUser). Org membership verification
is deferred to EP-11 — for now we validate the JWT and trust the
organization_id query parameter, matching the EP-09 pattern.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, UTC
from decimal import Decimal
from typing import Annotated

import structlog
from fastapi import APIRouter, Query

from app.api.deps import DbDep
from app.auth.dependencies import CurrentUser
from app.dashboard.service import DashboardService
from app.schemas.dashboard import (
    KPIResponse,
    ModelBreakdownResponse,
    ModelMetrics,
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
    _user: CurrentUser,
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
    _user: CurrentUser,
    organization_id: Annotated[uuid.UUID, Query(description="Organization ID")],
    start_date: Annotated[date, Query(description="Start date (inclusive)")],
    end_date: Annotated[date, Query(description="End date (inclusive)")],
    granularity: Annotated[str, Query(description="Bucket size: daily, weekly, monthly")] = "daily",
    currency: Annotated[str, Query(description="Target currency")] = "USD",
) -> TimeSeriesResponse:
    """Return time-bucketed cost data for an organization."""
    svc = DashboardService(session=db)
    points_data = await svc.get_time_series(
        organization_id, start_date, end_date, granularity=granularity
    )
    points = [
        TimeSeriesPoint(
            date=p["date"],
            cost=str(p["cost"]),
            tokens=p["tokens"],
            requests=p["requests"],
            currency=p.get("currency", currency),
        )
        for p in points_data
    ]
    total_cost = sum((p["cost"] for p in points_data), Decimal(0))
    total_tokens = sum(p["tokens"] for p in points_data)
    total_requests = sum(p["requests"] for p in points_data)
    return TimeSeriesResponse(
        granularity=granularity,
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
    _user: CurrentUser,
    organization_id: Annotated[uuid.UUID, Query(description="Organization ID")],
    start_date: Annotated[date, Query(description="Start date (inclusive)")],
    end_date: Annotated[date, Query(description="End date (inclusive)")],
    currency: Annotated[str, Query(description="Target currency")] = "USD",
) -> ProviderBreakdownResponse:
    """Return provider-level cost breakdown."""
    svc = DashboardService(session=db)
    rows = await svc.get_provider_breakdown(organization_id, start_date, end_date)
    providers = [
        ProviderMetrics(
            provider=r["provider"],
            total_cost=str(r["total_cost"]),
            total_tokens=r["total_tokens"],
            total_requests=r["total_requests"],
            avg_cost_per_request=str(r["avg_cost_per_request"]),
            currency=r.get("currency", currency),
        )
        for r in rows
    ]
    total_cost = sum((r["total_cost"] for r in rows), Decimal(0))
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
    _user: CurrentUser,
    organization_id: Annotated[uuid.UUID, Query(description="Organization ID")],
    start_date: Annotated[date, Query(description="Start date (inclusive)")],
    end_date: Annotated[date, Query(description="End date (inclusive)")],
    limit: Annotated[int, Query(description="Maximum models to return", ge=1, le=100)] = 20,
    currency: Annotated[str, Query(description="Target currency")] = "USD",
) -> ModelBreakdownResponse:
    """Return model-level cost breakdown."""
    svc = DashboardService(session=db)
    rows = await svc.get_model_breakdown(organization_id, start_date, end_date, limit=limit)
    models = [
        ModelMetrics(
            provider=r["provider"],
            model=r["model"],
            total_cost=str(r["total_cost"]),
            total_tokens=r["total_tokens"],
            total_requests=r["total_requests"],
            avg_cost_per_request=str(r["avg_cost_per_request"]),
            currency=r.get("currency", currency),
        )
        for r in rows
    ]
    total_cost = sum((r["total_cost"] for r in rows), Decimal(0))
    return ModelBreakdownResponse(
        models=models,
        total_cost=str(total_cost),
        period_start=start_date.isoformat(),
        period_end=end_date.isoformat(),
    )


# ── F-064 Organization Dashboard ──────────────────────────────────────────────


@router.get(
    "/organization",
    summary="Composite organization dashboard",
    description=(
        "Returns a combined response with overview metrics, provider breakdown, "
        "top 5 models, project breakdown, and daily cost trend (last 30 days)."
    ),
)
async def get_organization_dashboard(
    db: DbDep,
    _user: CurrentUser,
    organization_id: Annotated[uuid.UUID, Query(description="Organization ID")],
    start_date: Annotated[date | None, Query(description="Start date (defaults to first of current month)")] = None,
    end_date: Annotated[date | None, Query(description="End date (defaults to today)")] = None,
    currency: Annotated[str, Query(description="Target currency")] = "USD",
) -> dict:
    """Return composite organization dashboard."""
    today = datetime.now(tz=UTC).date()
    effective_end = end_date or today
    effective_start = start_date or effective_end.replace(day=1)

    svc = DashboardService(session=db)

    overview_data = await svc.get_overview(organization_id, today=today)
    provider_rows = await svc.get_provider_breakdown(organization_id, effective_start, effective_end)
    model_rows = await svc.get_model_breakdown(organization_id, effective_start, effective_end, limit=5)
    project_rows = await svc.get_project_breakdown(organization_id, effective_start, effective_end)

    from datetime import timedelta
    trend_start = today - timedelta(days=29)
    trend_rows = await svc.get_time_series(organization_id, trend_start, today, granularity="daily")

    return {
        "organization_id": str(organization_id),
        "period_start": effective_start.isoformat(),
        "period_end": effective_end.isoformat(),
        "currency": currency,
        "overview": {
            "total_spend": str(overview_data["total_spend"]),
            "today_spend": str(overview_data["today_spend"]),
            "month_spend": str(overview_data["month_spend"]),
            "total_tokens": overview_data["total_tokens"],
            "total_requests": overview_data["total_requests"],
            "active_providers": overview_data["active_providers"],
            "active_models": overview_data["active_models"],
            "collection_status": overview_data["collection_status"],
            "last_collection_at": overview_data["last_collection_at"].isoformat()
            if overview_data["last_collection_at"]
            else None,
        },
        "provider_breakdown": [
            {
                "provider": r["provider"],
                "total_cost": str(r["total_cost"]),
                "total_tokens": r["total_tokens"],
                "total_requests": r["total_requests"],
                "avg_cost_per_request": str(r["avg_cost_per_request"]),
                "currency": r.get("currency", currency),
            }
            for r in provider_rows
        ],
        "top_models": [
            {
                "provider": r["provider"],
                "model": r["model"],
                "total_cost": str(r["total_cost"]),
                "total_tokens": r["total_tokens"],
                "total_requests": r["total_requests"],
                "avg_cost_per_request": str(r["avg_cost_per_request"]),
                "currency": r.get("currency", currency),
            }
            for r in model_rows
        ],
        "project_breakdown": [
            {
                "project_id": r["project_id"],
                "total_cost": str(r["total_cost"]),
                "total_tokens": r["total_tokens"],
                "total_requests": r["total_requests"],
                "currency": r.get("currency", currency),
            }
            for r in project_rows
        ],
        "daily_trend": [
            {
                "date": p["date"],
                "cost": str(p["cost"]),
                "tokens": p["tokens"],
                "requests": p["requests"],
                "currency": p.get("currency", currency),
            }
            for p in trend_rows
        ],
    }


# ── F-065 Project Dashboard ───────────────────────────────────────────────────


@router.get(
    "/projects",
    response_model=ProjectBreakdownResponse,
    summary="Project cost breakdown",
    description="Returns cost and usage metrics grouped by project.",
)
async def get_project_breakdown(
    db: DbDep,
    _user: CurrentUser,
    organization_id: Annotated[uuid.UUID, Query(description="Organization ID")],
    start_date: Annotated[date, Query(description="Start date (inclusive)")],
    end_date: Annotated[date, Query(description="End date (inclusive)")],
    currency: Annotated[str, Query(description="Target currency")] = "USD",
) -> ProjectBreakdownResponse:
    """Return project-level cost breakdown."""
    svc = DashboardService(session=db)
    rows = await svc.get_project_breakdown(organization_id, start_date, end_date)
    projects = [
        ProjectMetrics(
            project_id=r["project_id"],
            total_cost=str(r["total_cost"]),
            total_tokens=r["total_tokens"],
            total_requests=r["total_requests"],
            currency=r.get("currency", currency),
        )
        for r in rows
    ]
    total_cost = sum((r["total_cost"] for r in rows), Decimal(0))
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
    _user: CurrentUser,
    organization_id: Annotated[uuid.UUID, Query(description="Organization ID")],
    start_date: Annotated[date, Query(description="Start date (inclusive)")],
    end_date: Annotated[date, Query(description="End date (inclusive)")],
    currency: Annotated[str, Query(description="Target currency")] = "USD",
) -> KPIResponse:
    """Return derived KPIs for an organization."""
    svc = DashboardService(session=db)
    data = await svc.get_kpis(organization_id, start_date, end_date)
    return KPIResponse(
        highest_cost_provider=data["highest_cost_provider"],
        highest_cost_model=data["highest_cost_model"],
        avg_cost_per_request=str(data["avg_cost_per_request"])
        if data["avg_cost_per_request"] is not None
        else None,
        avg_cost_per_token=str(data["avg_cost_per_token"])
        if data["avg_cost_per_token"] is not None
        else None,
        period_start=start_date.isoformat(),
        period_end=end_date.isoformat(),
        currency=currency,
    )
