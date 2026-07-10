"""BudgetEvaluationService — EP-24.2.

The thin evaluation layer the ticket asked for: it computes nothing itself
beyond period-window math and a deterministic linear forecast (see
app/budgets/period.py and `_forecast()` below) — every spend number comes
from `UsageCostRecordRepository`'s existing dimension-filtered aggregate
queries (the exact ones EP-24.1's Analytics/Overview pages already use),
and every alert fired goes through the existing `AlertService.fire()`
(EP-19.3), reusing its dedup/suppression/EventBus-publish machinery as-is.

No second analytics engine. No second scheduler. No second notification
pipeline.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.dedup import budget_threshold_scope
from app.alerts.dispatcher import AlertService
from app.budgets.period import PeriodWindow, period_key, resolve_period_window
from app.models.alert import AlertSeverity, AlertType
from app.models.budget import Budget, BudgetScopeType
from app.repositories.budget_repository import BudgetRepository
from app.repositories.usage_cost_record_repository import UsageCostRecordRepository

log = structlog.get_logger(__name__)

_ZERO = Decimal(0)


@dataclass(slots=True)
class BudgetEvaluation:
    """Computed spend/forecast/status for one budget as of one evaluation
    moment — the raw data both the API (converted to `BudgetStatusSummary`)
    and the alert-firing pass below consume."""

    budget: Budget
    window: PeriodWindow
    current_spend: Decimal
    remaining: Decimal
    percent_used: float
    projected_period_spend: Decimal
    remaining_daily_allowance: Decimal
    status: str
    thresholds_crossed: list[float]

    @property
    def highest_threshold_crossed(self) -> float | None:
        return max(self.thresholds_crossed) if self.thresholds_crossed else None


def _status_for(percent_used: float) -> str:
    if percent_used >= 100:
        return "exceeded"
    if percent_used >= 90:
        return "critical"
    if percent_used >= 75:
        return "warning"
    return "healthy"


def _severity_for_threshold(threshold_pct: float) -> AlertSeverity:
    if threshold_pct >= 110:
        return AlertSeverity.CRITICAL
    if threshold_pct >= 100:
        return AlertSeverity.HIGH
    if threshold_pct >= 90:
        return AlertSeverity.MEDIUM
    if threshold_pct >= 75:
        return AlertSeverity.LOW
    return AlertSeverity.INFO


def _alert_type_for_threshold(threshold_pct: float) -> AlertType:
    return AlertType.BUDGET_EXCEEDED if threshold_pct >= 100 else AlertType.BUDGET_THRESHOLD


class BudgetEvaluationService:
    """Reads budgets via `BudgetRepository`, computes spend via
    `UsageCostRecordRepository` (never a second aggregation path), and
    optionally fires alerts via the existing `AlertService`.

    `alert_service=None` gives a read-only evaluator — used by the
    dashboard's `GET /v1/dashboard/budget-summary` and the Budgets page's
    `GET /v1/budgets`, which must never have a side effect of firing
    alerts just because a user opened a page.
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        alert_service: AlertService | None = None,
    ) -> None:
        self._session = session
        self._budgets = BudgetRepository(session)
        self._cost_records = UsageCostRecordRepository(session)
        self._alert_service = alert_service

    async def evaluate_budget(
        self, budget: Budget, *, today: date | None = None
    ) -> BudgetEvaluation:
        resolved_today = today or datetime.now(UTC).date()
        window = resolve_period_window(budget, today=resolved_today)

        project_id: uuid.UUID | None = None
        provider: str | None = None
        model: str | None = None
        if budget.scope_type == BudgetScopeType.PROJECT:
            project_id = budget.scope_project_id
        elif budget.scope_type == BudgetScopeType.PROVIDER:
            provider = budget.scope_provider
        elif budget.scope_type == BudgetScopeType.MODEL:
            model = budget.scope_model

        totals = await self._cost_records.get_totals_by_org(
            budget.organization_id,
            window.start,
            window.end,
            project_id=project_id,
            provider=provider,
            model=model,
        )
        current_spend = next(
            (row["total_cost"] for row in totals if row["currency"] == budget.currency), _ZERO
        )

        remaining = budget.amount - current_spend
        percent_used = float(current_spend / budget.amount * 100) if budget.amount > 0 else 0.0

        projected_period_spend, remaining_daily_allowance = _forecast(budget, window, current_spend)

        status = _status_for(percent_used)
        thresholds_crossed = sorted(t for t in budget.threshold_percentages if percent_used >= t)

        return BudgetEvaluation(
            budget=budget,
            window=window,
            current_spend=current_spend,
            remaining=remaining,
            percent_used=percent_used,
            projected_period_spend=projected_period_spend,
            remaining_daily_allowance=remaining_daily_allowance,
            status=status,
            thresholds_crossed=thresholds_crossed,
        )

    async def evaluate_organization(
        self, organization_id: uuid.UUID, *, today: date | None = None
    ) -> list[BudgetEvaluation]:
        """Evaluate every enabled budget for one organization. Read-only —
        never fires alerts. Used by the dashboard summary/budgets-list
        reads (via a service with `alert_service=None`) and as the first
        half of `evaluate_and_alert()` below."""
        budgets = await self._budgets.list_enabled_for_org(organization_id)
        return [await self.evaluate_budget(b, today=today) for b in budgets]

    async def evaluate_and_alert(
        self, organization_id: uuid.UUID, *, today: date | None = None
    ) -> list[BudgetEvaluation]:
        """The post-sync hook: evaluate every enabled budget for one
        organization and fire an alert for every threshold currently
        crossed. Called from `UsageSyncScheduler` after a successful
        background sync and from the manual-sync API handlers — the same
        method, not two evaluation paths (see CLAUDE.md's EP-24.2 section).

        Firing is idempotent per (budget, period, threshold): `AlertService
        .fire()`'s existing dedup keys off exactly that tuple
        (`budget_threshold_scope`), so re-evaluating an already-crossed
        threshold within the same period just folds into the existing OPEN
        alert (`occurrence_count` increments) instead of creating a
        duplicate — evaluating budgets multiple times is therefore safe,
        not just "not wrong."
        """
        if self._alert_service is None:
            raise RuntimeError(
                "evaluate_and_alert() requires a BudgetEvaluationService constructed "
                "with alert_service — use evaluate_organization() for read-only reads."
            )

        evaluations = await self.evaluate_organization(organization_id, today=today)
        for evaluation in evaluations:
            await self._fire_for_evaluation(evaluation)
        return evaluations

    async def _fire_for_evaluation(self, evaluation: BudgetEvaluation) -> None:
        if self._alert_service is None:  # pragma: no cover - guarded by caller
            return
        budget = evaluation.budget
        pkey = period_key(budget, evaluation.window)
        for threshold in evaluation.thresholds_crossed:
            scope = budget_threshold_scope(budget.id, pkey, threshold)
            alert_type = _alert_type_for_threshold(threshold)
            severity = _severity_for_threshold(threshold)
            scope_label = _scope_label(budget)
            title = (
                f"{budget.name}: {threshold:g}% threshold reached"
                if alert_type == AlertType.BUDGET_THRESHOLD
                else f"{budget.name}: budget exceeded ({threshold:g}%)"
            )
            message = (
                f"{scope_label} has spent {evaluation.current_spend} {budget.currency} "
                f"of its {budget.amount} {budget.currency} {budget.period.value} budget "
                f"({evaluation.percent_used:.1f}% used)."
            )
            try:
                await self._alert_service.fire(
                    organization_id=budget.organization_id,
                    alert_type=alert_type,
                    severity=severity,
                    title=title,
                    message=message,
                    source="budget_evaluation",
                    scope=scope,
                    provider=budget.scope_provider,
                    metadata={
                        "budget_id": str(budget.id),
                        "budget_name": budget.name,
                        "scope_type": budget.scope_type.value,
                        "threshold_pct": threshold,
                        "percent_used": round(evaluation.percent_used, 2),
                        "current_spend": str(evaluation.current_spend),
                        "amount": str(budget.amount),
                        "currency": budget.currency,
                        "period_start": evaluation.window.start.isoformat(),
                        "period_end": evaluation.window.end.isoformat(),
                    },
                )
            except Exception:  # never let one budget's alert failure abort a sync
                log.warning(
                    "budget_alert_fire_failed",
                    budget_id=str(budget.id),
                    threshold=threshold,
                    exc_info=True,
                )


def _scope_label(budget: Budget) -> str:
    if budget.scope_type == BudgetScopeType.ORGANIZATION:
        return "This organization"
    if budget.scope_type == BudgetScopeType.PROJECT:
        return "This project"
    if budget.scope_type == BudgetScopeType.PROVIDER:
        return f"Provider {budget.scope_provider}"
    return f"Model {budget.scope_model}"


def _forecast(
    budget: Budget, window: PeriodWindow, current_spend: Decimal
) -> tuple[Decimal, Decimal]:
    """Deterministic baseline forecast — no machine learning, per the
    ticket's explicit instruction:

      projected_period_spend    = current_spend / days_elapsed * total_days
                                   (linear extrapolation of the run-rate
                                   observed so far this period)
      remaining_daily_allowance = (amount - current_spend) / days_remaining
                                   (how much more can be spent per day for
                                   the rest of the period without exceeding
                                   the budget)

    Both are zero-division-guarded: a period that just started (0 days
    elapsed) projects its current spend unchanged rather than dividing by
    zero; a period on or past its last day has no "remaining daily
    allowance" left to compute.
    """
    if window.days_elapsed <= 0:
        projected_period_spend = current_spend
    else:
        projected_period_spend = (current_spend / window.days_elapsed) * window.total_days

    if window.days_remaining <= 0:
        remaining_daily_allowance = _ZERO
    else:
        remaining_daily_allowance = (budget.amount - current_spend) / window.days_remaining

    return projected_period_spend, remaining_daily_allowance
