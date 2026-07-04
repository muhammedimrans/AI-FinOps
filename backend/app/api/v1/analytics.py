"""Analytics API endpoints — F-053 (EP-09).

Endpoints
---------
GET /analytics/usage                        — usage summary for org
GET /analytics/cost                         — cost summary for org
GET /analytics/providers                    — per-provider cost breakdown
GET /analytics/models                       — per-model cost breakdown
GET /analytics/projects                     — per-project cost breakdown
GET /analytics/organizations/{org_id}/summary — combined org summary

Authentication
--------------
All endpoints require a valid JWT AND verified membership of the requested
organization (OrgScopedMembership) — the organization_id query parameter is
never trusted without a membership check.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

import structlog
from fastapi import APIRouter, Query

from app.analytics.service import AnalyticsService
from app.api.deps import DbDep
from app.auth.dependencies import CurrentMembership, OrgScopedMembership
from app.repositories.daily_cost_summary_repository import DailyCostSummaryRepository
from app.repositories.usage_cost_record_repository import UsageCostRecordRepository
from app.schemas.analytics import (
    CostByCurrencyItem,
    CostSummaryResponse,
    ModelBreakdownItem,
    OrgSummaryResponse,
    ProjectBreakdownItem,
    ProviderBreakdownItem,
    UsageSummaryResponse,
)

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _make_service(db: object) -> AnalyticsService:
    """Build AnalyticsService from a DB session."""
    return AnalyticsService(
        cost_record_repo=UsageCostRecordRepository(db),  # type: ignore[arg-type]
        daily_summary_repo=DailyCostSummaryRepository(db),  # type: ignore[arg-type]
    )


# ── Usage summary ──────────────────────────────────────────────────────────────


@router.get(
    "/usage",
    response_model=UsageSummaryResponse,
    summary="Usage summary for organization",
    description=(
        "Returns total token counts and request count for the organization "
        "in the specified date range."
    ),
)
async def get_usage_summary(
    db: DbDep,
    _member: OrgScopedMembership,
    organization_id: Annotated[uuid.UUID, Query(description="Organization ID")],
    start_date: Annotated[date, Query(description="Start date (inclusive)")],
    end_date: Annotated[date, Query(description="End date (inclusive)")],
) -> UsageSummaryResponse:
    """Return usage summary for an organization."""
    service = _make_service(db)
    summary = await service.get_usage_summary(organization_id, start_date, end_date)
    return UsageSummaryResponse(**summary)


# ── Cost summary ───────────────────────────────────────────────────────────────


@router.get(
    "/cost",
    response_model=CostSummaryResponse,
    summary="Cost summary for organization",
    description="Returns total costs for the organization in the specified date range.",
)
async def get_cost_summary(
    db: DbDep,
    _member: OrgScopedMembership,
    organization_id: Annotated[uuid.UUID, Query(description="Organization ID")],
    start_date: Annotated[date, Query(description="Start date (inclusive)")],
    end_date: Annotated[date, Query(description="End date (inclusive)")],
) -> CostSummaryResponse:
    """Return cost summary for an organization."""
    service = _make_service(db)
    summary = await service.get_cost_summary(organization_id, start_date, end_date)
    return CostSummaryResponse(
        organization_id=summary["organization_id"],
        start_date=summary["start_date"],
        end_date=summary["end_date"],
        cost_by_currency=[
            CostByCurrencyItem(
                currency=c["currency"],
                total_cost=str(c["total_cost"]),
                total_tokens=c["total_tokens"],
                record_count=c["record_count"],
            )
            for c in summary["cost_by_currency"]
        ],
        total_cost=str(summary["total_cost"]),
        total_tokens=summary["total_tokens"],
        record_count=summary["record_count"],
    )


# ── Provider breakdown ─────────────────────────────────────────────────────────


@router.get(
    "/providers",
    response_model=list[ProviderBreakdownItem],
    summary="Per-provider cost breakdown",
    description="Returns cost and token breakdown grouped by provider.",
)
async def get_provider_breakdown(
    db: DbDep,
    _member: OrgScopedMembership,
    organization_id: Annotated[uuid.UUID, Query(description="Organization ID")],
    start_date: Annotated[date, Query(description="Start date (inclusive)")],
    end_date: Annotated[date, Query(description="End date (inclusive)")],
) -> list[ProviderBreakdownItem]:
    """Return cost breakdown by provider."""
    service = _make_service(db)
    rows = await service.get_provider_breakdown(organization_id, start_date, end_date)
    return [
        ProviderBreakdownItem(
            provider=r["provider"],
            currency=r["currency"],
            total_cost=str(r["total_cost"]),
            total_prompt_cost=str(r["total_prompt_cost"]),
            total_completion_cost=str(r["total_completion_cost"]),
            total_tokens=r["total_tokens"],
            total_prompt_tokens=r["total_prompt_tokens"],
            total_completion_tokens=r["total_completion_tokens"],
            record_count=r["record_count"],
        )
        for r in rows
    ]


# ── Model breakdown ────────────────────────────────────────────────────────────


@router.get(
    "/models",
    response_model=list[ModelBreakdownItem],
    summary="Per-model cost breakdown",
    description="Returns cost and token breakdown grouped by model.",
)
async def get_model_breakdown(
    db: DbDep,
    _member: OrgScopedMembership,
    organization_id: Annotated[uuid.UUID, Query(description="Organization ID")],
    start_date: Annotated[date, Query(description="Start date (inclusive)")],
    end_date: Annotated[date, Query(description="End date (inclusive)")],
    provider: Annotated[str | None, Query()] = None,
) -> list[ModelBreakdownItem]:
    """Return cost breakdown by model."""
    service = _make_service(db)
    rows = await service.get_model_breakdown(organization_id, start_date, end_date)

    # Optional provider filter
    if provider:
        rows = [r for r in rows if r["provider"] == provider]

    return [
        ModelBreakdownItem(
            provider=r["provider"],
            model=r["model"],
            currency=r["currency"],
            total_cost=str(r["total_cost"]),
            total_prompt_cost=str(r["total_prompt_cost"]),
            total_completion_cost=str(r["total_completion_cost"]),
            total_tokens=r["total_tokens"],
            total_prompt_tokens=r["total_prompt_tokens"],
            total_completion_tokens=r["total_completion_tokens"],
            record_count=r["record_count"],
        )
        for r in rows
    ]


# ── Project breakdown ──────────────────────────────────────────────────────────


@router.get(
    "/projects",
    response_model=list[ProjectBreakdownItem],
    summary="Per-project cost breakdown",
    description="Returns cost breakdown grouped by project.",
)
async def get_project_breakdown(
    db: DbDep,
    _member: OrgScopedMembership,
    organization_id: Annotated[uuid.UUID, Query(description="Organization ID")],
    start_date: Annotated[date, Query(description="Start date (inclusive)")],
    end_date: Annotated[date, Query(description="End date (inclusive)")],
) -> list[ProjectBreakdownItem]:
    """Return cost breakdown by project."""
    service = _make_service(db)
    rows = await service.get_project_breakdown(organization_id, start_date, end_date)
    return [
        ProjectBreakdownItem(
            project_id=str(r["project_id"]) if r["project_id"] is not None else None,
            currency=r["currency"],
            total_cost=str(r["total_cost"]),
            total_tokens=r["total_tokens"],
            record_count=r["record_count"],
        )
        for r in rows
    ]


# ── Org summary ────────────────────────────────────────────────────────────────


@router.get(
    "/organizations/{org_id}/summary",
    response_model=OrgSummaryResponse,
    summary="Combined org usage and cost summary",
    description=(
        "Returns a combined usage and cost summary for the organization "
        "in the specified date range."
    ),
)
async def get_org_summary(
    org_id: uuid.UUID,
    db: DbDep,
    _member: CurrentMembership,
    start_date: Annotated[date, Query(description="Start date (inclusive)")],
    end_date: Annotated[date, Query(description="End date (inclusive)")],
) -> OrgSummaryResponse:
    """Return combined usage and cost summary for an organization."""
    service = _make_service(db)
    usage = await service.get_usage_summary(org_id, start_date, end_date)
    cost = await service.get_cost_summary(org_id, start_date, end_date)
    return OrgSummaryResponse(
        organization_id=str(org_id),
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        total_tokens=usage["total_tokens"],
        total_prompt_tokens=usage["total_prompt_tokens"],
        total_completion_tokens=usage["total_completion_tokens"],
        total_requests=usage["total_requests"],
        event_count=usage["event_count"],
        cost_by_currency=[
            CostByCurrencyItem(
                currency=c["currency"],
                total_cost=str(c["total_cost"]),
                total_tokens=c["total_tokens"],
                record_count=c["record_count"],
            )
            for c in cost["cost_by_currency"]
        ],
        total_cost=str(cost["total_cost"]),
    )
