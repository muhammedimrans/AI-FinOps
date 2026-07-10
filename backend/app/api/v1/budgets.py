"""Budgets API — EP-24.2.

Endpoints
---------
GET    /v1/budgets              — list budgets for an organization, each with
                                   its current derived spend/forecast/status
                                   (read-only — never fires alerts)
POST   /v1/budgets              — create a budget
PATCH  /v1/budgets/{budget_id}  — partial update
DELETE /v1/budgets/{budget_id}  — soft-delete

Authorization: same convention as /v1/alerts (EP-19.3) — `organization_id`
as a query parameter, `RequireQueryPermission`, reusing `NOTIFICATION_READ`/
`NOTIFICATION_WRITE` rather than inventing a new permission (budgets are an
org-configurable alerting concern, exactly like alert rules already are —
MEMBER+ can already create/write alert rules under this permission).

Spend/forecast for every budget in the list response comes from
`BudgetEvaluationService`, which itself only calls
`UsageCostRecordRepository`'s existing aggregate queries — no duplicate
aggregation logic here.
"""

from __future__ import annotations

import enum
import uuid
from decimal import Decimal, InvalidOperation
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import DbDep
from app.auth.dependencies import CurrentUser, RequireQueryPermission
from app.auth.rbac import Permission
from app.budgets.service import BudgetEvaluation, BudgetEvaluationService
from app.models.budget import Budget, BudgetPeriod, BudgetScopeType
from app.repositories.budget_repository import BudgetRepository
from app.schemas.budgets import (
    BudgetResponse,
    BudgetsListResponse,
    BudgetStatusSummary,
    CreateBudgetRequest,
    UpdateBudgetRequest,
)

router = APIRouter(prefix="/budgets", tags=["budgets"])


def _parse_decimal(value: str, field: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid decimal value for {field!r}: {value!r}",
        ) from exc
    if parsed <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{field} must be greater than zero",
        )
    return parsed


def _parse_enum_value[EnumT: enum.Enum](enum_cls: type[EnumT], value: str, field: str) -> EnumT:
    try:
        return enum_cls(value)
    except ValueError as exc:
        allowed = [m.value for m in enum_cls]
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid {field} {value!r}. Must be one of: {allowed}",
        ) from exc


def _to_response(budget: Budget) -> BudgetResponse:
    return BudgetResponse(
        id=budget.id,
        organization_id=budget.organization_id,
        name=budget.name,
        scope_type=budget.scope_type.value,
        scope_project_id=budget.scope_project_id,
        scope_provider=budget.scope_provider,
        scope_model=budget.scope_model,
        amount=str(budget.amount),
        currency=budget.currency,
        period=budget.period.value,
        custom_period_start=budget.custom_period_start,
        custom_period_end=budget.custom_period_end,
        threshold_percentages=budget.threshold_percentages,
        enabled=budget.enabled,
        created_by=budget.created_by,
        created_at=budget.created_at,
        updated_at=budget.updated_at,
    )


def _to_status_summary(evaluation: BudgetEvaluation) -> BudgetStatusSummary:
    return BudgetStatusSummary(
        budget=_to_response(evaluation.budget),
        current_spend=str(evaluation.current_spend),
        remaining=str(evaluation.remaining),
        percent_used=round(evaluation.percent_used, 2),
        period_start=evaluation.window.start,
        period_end=evaluation.window.end,
        days_elapsed=evaluation.window.days_elapsed,
        days_remaining=evaluation.window.days_remaining,
        projected_period_spend=str(evaluation.projected_period_spend),
        remaining_daily_allowance=str(evaluation.remaining_daily_allowance),
        status=evaluation.status,
        highest_threshold_crossed=evaluation.highest_threshold_crossed,
    )


async def _get_owned_budget(
    repo: BudgetRepository, org_id: uuid.UUID, budget_id: uuid.UUID
) -> Budget:
    budget = await repo.get_for_org(org_id, budget_id)
    if budget is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found")
    return budget


@router.get(
    "",
    response_model=BudgetsListResponse,
    summary="List budgets for an organization, each with derived spend/forecast/status",
)
async def list_budgets(
    db: DbDep,
    _member: Annotated[object, RequireQueryPermission(Permission.NOTIFICATION_READ)],
    organization_id: Annotated[uuid.UUID, Query(description="Organization ID")],
) -> BudgetsListResponse:
    repo = BudgetRepository(db)
    budgets = await repo.list_for_org(organization_id)
    return BudgetsListResponse(budgets=[_to_response(b) for b in budgets], total=len(budgets))


@router.post(
    "",
    response_model=BudgetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a budget",
)
async def create_budget(
    body: CreateBudgetRequest,
    db: DbDep,
    current_user: CurrentUser,
    _member: Annotated[object, RequireQueryPermission(Permission.NOTIFICATION_WRITE)],
    organization_id: Annotated[uuid.UUID, Query(description="Organization ID")],
) -> BudgetResponse:
    scope_type = _parse_enum_value(BudgetScopeType, body.scope_type, "scope_type")
    period = _parse_enum_value(BudgetPeriod, body.period, "period")

    if scope_type == BudgetScopeType.PROJECT and body.scope_project_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="scope_project_id is required when scope_type is 'project'",
        )
    if scope_type == BudgetScopeType.PROVIDER and not body.scope_provider:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="scope_provider is required when scope_type is 'provider'",
        )
    if scope_type == BudgetScopeType.MODEL and not body.scope_model:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="scope_model is required when scope_type is 'model'",
        )
    if period == BudgetPeriod.CUSTOM and (
        body.custom_period_start is None or body.custom_period_end is None
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="custom_period_start and custom_period_end are required when period is 'custom'",
        )

    amount = _parse_decimal(body.amount, "amount")

    scope_project_id = body.scope_project_id if scope_type == BudgetScopeType.PROJECT else None
    scope_provider = body.scope_provider if scope_type == BudgetScopeType.PROVIDER else None
    scope_model = body.scope_model if scope_type == BudgetScopeType.MODEL else None

    repo = BudgetRepository(db)
    budget = await repo.create(
        Budget(
            organization_id=organization_id,
            name=body.name,
            scope_type=scope_type,
            scope_project_id=scope_project_id,
            scope_provider=scope_provider,
            scope_model=scope_model,
            amount=amount,
            currency=body.currency,
            period=period,
            custom_period_start=body.custom_period_start if period == BudgetPeriod.CUSTOM else None,
            custom_period_end=body.custom_period_end if period == BudgetPeriod.CUSTOM else None,
            threshold_percentages=body.threshold_percentages,
            enabled=body.enabled,
            created_by=current_user.id,
        )
    )
    return _to_response(budget)


@router.patch(
    "/{budget_id}",
    response_model=BudgetResponse,
    summary="Partially update a budget",
)
async def update_budget(
    budget_id: uuid.UUID,
    body: UpdateBudgetRequest,
    db: DbDep,
    _member: Annotated[object, RequireQueryPermission(Permission.NOTIFICATION_WRITE)],
    organization_id: Annotated[uuid.UUID, Query(description="Organization ID")],
) -> BudgetResponse:
    repo = BudgetRepository(db)
    budget = await _get_owned_budget(repo, organization_id, budget_id)

    updates: dict[str, object] = {}
    fields = body.model_dump(exclude_unset=True)
    if "name" in fields:
        updates["name"] = fields["name"]
    if "amount" in fields:
        updates["amount"] = _parse_decimal(fields["amount"], "amount")
    if "currency" in fields:
        updates["currency"] = fields["currency"]
    if "period" in fields:
        updates["period"] = _parse_enum_value(BudgetPeriod, fields["period"], "period")
    if "custom_period_start" in fields:
        updates["custom_period_start"] = fields["custom_period_start"]
    if "custom_period_end" in fields:
        updates["custom_period_end"] = fields["custom_period_end"]
    if "threshold_percentages" in fields:
        thresholds = fields["threshold_percentages"]
        if not thresholds or any(t <= 0 for t in thresholds):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="threshold_percentages must be a non-empty list of positive numbers",
            )
        updates["threshold_percentages"] = sorted(set(thresholds))
    if "enabled" in fields:
        updates["enabled"] = fields["enabled"]

    updated = await repo.update(budget, **updates) if updates else budget
    return _to_response(updated)


@router.delete(
    "/{budget_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a budget",
)
async def delete_budget(
    budget_id: uuid.UUID,
    db: DbDep,
    current_user: CurrentUser,
    _member: Annotated[object, RequireQueryPermission(Permission.NOTIFICATION_WRITE)],
    organization_id: Annotated[uuid.UUID, Query(description="Organization ID")],
) -> None:
    repo = BudgetRepository(db)
    budget = await _get_owned_budget(repo, organization_id, budget_id)
    await repo.soft_delete(budget, deleted_by=current_user.id)


@router.get(
    "/{budget_id}/status",
    response_model=BudgetStatusSummary,
    summary="Derived spend/forecast/status for one budget (read-only)",
)
async def get_budget_status(
    budget_id: uuid.UUID,
    db: DbDep,
    _member: Annotated[object, RequireQueryPermission(Permission.NOTIFICATION_READ)],
    organization_id: Annotated[uuid.UUID, Query(description="Organization ID")],
) -> BudgetStatusSummary:
    repo = BudgetRepository(db)
    budget = await _get_owned_budget(repo, organization_id, budget_id)
    evaluator = BudgetEvaluationService(db)  # read-only — no alert_service
    evaluation = await evaluator.evaluate_budget(budget)
    return _to_status_summary(evaluation)
