"""Deterministic period-window calculation for budgets (EP-24.2).

Every period boundary here is computed directly from a `date` — no
database round-trip, no randomness, no external clock beyond the one
`today` value the caller passes in. Kept separate from
`BudgetEvaluationService` so the pure date math is trivially unit-testable
on its own.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

from app.models.budget import Budget, BudgetPeriod


@dataclass(frozen=True, slots=True)
class PeriodWindow:
    start: date
    end: date  # inclusive
    days_elapsed: int  # inclusive of `today`
    days_remaining: int  # inclusive of `today`... exclusive of `today` itself, see below

    @property
    def total_days(self) -> int:
        return (self.end - self.start).days + 1


def _month_end(year: int, month: int) -> date:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, last_day)


def resolve_period_window(budget: Budget, *, today: date) -> PeriodWindow:
    """Resolve the [start, end] window a budget's spend/threshold checks
    apply to, "as of" `today`. Deterministic: the same (budget, today)
    input always produces the same output.
    """
    period = budget.period

    if period == BudgetPeriod.DAILY:
        start = end = today
    elif period == BudgetPeriod.WEEKLY:
        # Monday-start week, matching ISO weekday numbering (Monday=0).
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
    elif period == BudgetPeriod.MONTHLY:
        start = today.replace(day=1)
        end = _month_end(today.year, today.month)
    elif period == BudgetPeriod.YEARLY:
        start = date(today.year, 1, 1)
        end = date(today.year, 12, 31)
    elif period == BudgetPeriod.CUSTOM:
        if budget.custom_period_start is None or budget.custom_period_end is None:
            # A custom budget with no configured window has nothing to
            # evaluate against — treat "today" as a single-day window
            # rather than raising, so a misconfigured budget degrades to
            # "always evaluates as if brand new" instead of crashing an
            # entire org's evaluation pass.
            start = end = today
        else:
            start = budget.custom_period_start
            end = budget.custom_period_end
    else:  # pragma: no cover - exhaustive over BudgetPeriod
        start = end = today

    if today < start:
        days_elapsed = 0
    elif today > end:
        days_elapsed = (end - start).days + 1
    else:
        days_elapsed = (today - start).days + 1

    total_days = (end - start).days + 1
    days_remaining = max(total_days - days_elapsed, 0)

    return PeriodWindow(
        start=start, end=end, days_elapsed=days_elapsed, days_remaining=days_remaining
    )


def period_key(budget: Budget, window: PeriodWindow) -> str:
    """A short, stable string identifying *which* occurrence of a budget's
    recurring period this is — used to qualify the alert dedup key
    (`app/alerts/dedup.py`'s `budget_threshold_scope`) so a new period never
    inherits a prior period's still-open alert."""
    if budget.period == BudgetPeriod.CUSTOM:
        return f"{window.start.isoformat()}:{window.end.isoformat()}"
    return window.start.isoformat()
