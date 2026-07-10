"""Request/response schemas for /v1/budgets and the budget-summary dashboard
endpoint (EP-24.2)."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator


class CreateBudgetRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    scope_type: str  # BudgetScopeType value
    scope_project_id: uuid.UUID | None = None
    scope_provider: str | None = Field(default=None, max_length=64)
    scope_model: str | None = Field(default=None, max_length=128)
    amount: str  # Decimal as string on the wire — avoids float precision loss
    currency: str = Field(default="USD", max_length=8)
    period: str  # BudgetPeriod value
    custom_period_start: date | None = None
    custom_period_end: date | None = None
    threshold_percentages: list[float] = Field(default_factory=lambda: [50.0, 75.0, 90.0, 100.0])
    enabled: bool = True

    @field_validator("threshold_percentages")
    @classmethod
    def _thresholds_positive(cls, v: list[float]) -> list[float]:
        if not v:
            raise ValueError("threshold_percentages must not be empty")
        if any(t <= 0 for t in v):
            raise ValueError("threshold_percentages must all be positive")
        return sorted(set(v))


class UpdateBudgetRequest(BaseModel):
    """Partial update — only supplied fields change (`exclude_unset`, matching
    the pattern `PATCH /v1/organizations/{id}`/`PATCH /v1/auth/me` already
    use)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    amount: str | None = None
    currency: str | None = Field(default=None, max_length=8)
    period: str | None = None
    custom_period_start: date | None = None
    custom_period_end: date | None = None
    threshold_percentages: list[float] | None = None
    enabled: bool | None = None


class BudgetResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    scope_type: str
    scope_project_id: uuid.UUID | None
    scope_provider: str | None
    scope_model: str | None
    amount: str
    currency: str
    period: str
    custom_period_start: date | None
    custom_period_end: date | None
    threshold_percentages: list[float]
    enabled: bool
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class BudgetsListResponse(BaseModel):
    budgets: list[BudgetResponse]
    total: int


class BudgetStatusSummary(BaseModel):
    """Derived spend/forecast state for one budget — the row shown on the
    Budgets page and folded into `GET /v1/dashboard/budget-summary`.

    Every number here comes from `UsageCostRecordRepository`'s existing
    dimension-filtered totals (via `BudgetEvaluationService`) — no
    duplicate aggregation, no second analytics engine.
    """

    budget: BudgetResponse
    current_spend: str
    remaining: str
    percent_used: float
    period_start: date
    period_end: date
    days_elapsed: int
    days_remaining: int
    projected_period_spend: str
    remaining_daily_allowance: str
    status: str  # healthy | warning | critical | exceeded
    highest_threshold_crossed: float | None


class BudgetSummaryResponse(BaseModel):
    """Powers both the Budgets page's per-budget cards and the Overview
    page's Budget Remaining / Active Alerts / Critical Alerts / Projected
    End-of-Month Spend KPI cards."""

    budgets: list[BudgetStatusSummary]
    currency: str
    total_budgeted: str
    total_spent: str
    total_remaining: str
    active_alert_count: int
    critical_alert_count: int
    projected_eom_spend: str
