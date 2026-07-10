"""EP-24.2 test suite — Budgets, Spend Alerts & Cost Monitoring.

Coverage targets:
- app.budgets.period: resolve_period_window for daily/weekly/monthly/yearly/
  custom periods, days_elapsed/days_remaining edge cases, period_key.
- app.alerts.dedup.budget_threshold_scope: qualified by (budget, period, threshold).
- BudgetEvaluationService: spend via UsageCostRecordRepository.get_totals_by_org
  (mocked — no duplicate aggregation query is exercised, only that the
  service calls the existing one), deterministic forecast math, status
  banding, threshold-crossing detection, evaluate_and_alert firing through
  the existing AlertService, idempotent re-evaluation.
- BudgetRepository: CRUD basics against a mocked session.
- API: GET/POST/PATCH/DELETE /v1/budgets (RBAC: VIEWER read-only, MEMBER+
  write), GET /v1/dashboard/budget-summary.
- UsageSyncScheduler: `_evaluate_budgets` is invoked after a successful
  sync when an EventBus is configured, and skipped when it is not.

All tests are hermetic — no network calls, no real database, matching the
convention every EP-19.3/EP-23.x/EP-24.1 test module already established.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.alerts.dedup import budget_threshold_scope
from app.budgets.period import period_key, resolve_period_window
from app.budgets.service import BudgetEvaluationService
from app.models.alert import AlertSeverity, AlertType
from app.models.budget import Budget, BudgetPeriod, BudgetScopeType
from app.models.membership import MembershipRole

_ORG_ID = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
_PROJECT_ID = uuid.UUID("00000000-0000-0000-0000-0000000000a2")
_BUDGET_ID = uuid.UUID("00000000-0000-0000-0000-0000000000a3")


def _make_budget(
    *,
    scope_type: BudgetScopeType = BudgetScopeType.ORGANIZATION,
    scope_project_id: uuid.UUID | None = None,
    scope_provider: str | None = None,
    scope_model: str | None = None,
    amount: Decimal = Decimal("100.00"),
    currency: str = "USD",
    period: BudgetPeriod = BudgetPeriod.MONTHLY,
    custom_period_start: date | None = None,
    custom_period_end: date | None = None,
    threshold_percentages: list[float] | None = None,
) -> Budget:
    b = Budget()
    b.id = _BUDGET_ID
    b.organization_id = _ORG_ID
    b.name = "Test Budget"
    b.scope_type = scope_type
    b.scope_project_id = scope_project_id
    b.scope_provider = scope_provider
    b.scope_model = scope_model
    b.amount = amount
    b.currency = currency
    b.period = period
    b.custom_period_start = custom_period_start
    b.custom_period_end = custom_period_end
    b.threshold_percentages = threshold_percentages or [50.0, 75.0, 90.0, 100.0]
    b.enabled = True
    b.created_by = None
    b.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    b.updated_at = datetime(2026, 1, 1, tzinfo=UTC)
    return b


# ══════════════════════════════════════════════════════════════════════════════
# app.budgets.period — deterministic period-window math
# ══════════════════════════════════════════════════════════════════════════════


class TestResolvePeriodWindow:
    def test_daily_window_is_single_day(self) -> None:
        budget = _make_budget(period=BudgetPeriod.DAILY)
        window = resolve_period_window(budget, today=date(2026, 6, 15))
        assert window.start == window.end == date(2026, 6, 15)
        assert window.days_elapsed == 1
        assert window.days_remaining == 0
        assert window.total_days == 1

    def test_weekly_window_is_monday_start(self) -> None:
        budget = _make_budget(period=BudgetPeriod.WEEKLY)
        # 2026-06-17 is a Wednesday
        window = resolve_period_window(budget, today=date(2026, 6, 17))
        assert window.start == date(2026, 6, 15)  # Monday
        assert window.end == date(2026, 6, 21)  # Sunday
        assert window.days_elapsed == 3
        assert window.days_remaining == 4

    def test_monthly_window_spans_full_calendar_month(self) -> None:
        budget = _make_budget(period=BudgetPeriod.MONTHLY)
        window = resolve_period_window(budget, today=date(2026, 2, 10))
        assert window.start == date(2026, 2, 1)
        assert window.end == date(2026, 2, 28)  # 2026 is not a leap year
        assert window.days_elapsed == 10
        assert window.days_remaining == 18

    def test_yearly_window_spans_full_calendar_year(self) -> None:
        budget = _make_budget(period=BudgetPeriod.YEARLY)
        window = resolve_period_window(budget, today=date(2026, 6, 15))
        assert window.start == date(2026, 1, 1)
        assert window.end == date(2026, 12, 31)
        assert window.total_days == 365

    def test_custom_window_uses_configured_bounds(self) -> None:
        budget = _make_budget(
            period=BudgetPeriod.CUSTOM,
            custom_period_start=date(2026, 3, 1),
            custom_period_end=date(2026, 3, 15),
        )
        window = resolve_period_window(budget, today=date(2026, 3, 5))
        assert window.start == date(2026, 3, 1)
        assert window.end == date(2026, 3, 15)
        assert window.days_elapsed == 5
        assert window.total_days == 15

    def test_custom_window_without_configured_bounds_degrades_to_today(self) -> None:
        budget = _make_budget(period=BudgetPeriod.CUSTOM)
        window = resolve_period_window(budget, today=date(2026, 3, 5))
        assert window.start == window.end == date(2026, 3, 5)

    def test_today_before_period_start_has_zero_elapsed(self) -> None:
        budget = _make_budget(
            period=BudgetPeriod.CUSTOM,
            custom_period_start=date(2026, 6, 1),
            custom_period_end=date(2026, 6, 30),
        )
        window = resolve_period_window(budget, today=date(2026, 5, 1))
        assert window.days_elapsed == 0
        assert window.days_remaining == 30

    def test_today_after_period_end_has_full_elapsed_zero_remaining(self) -> None:
        budget = _make_budget(
            period=BudgetPeriod.CUSTOM,
            custom_period_start=date(2026, 6, 1),
            custom_period_end=date(2026, 6, 10),
        )
        window = resolve_period_window(budget, today=date(2026, 7, 1))
        assert window.days_elapsed == 10
        assert window.days_remaining == 0

    def test_period_key_is_stable_for_the_same_month(self) -> None:
        budget = _make_budget(period=BudgetPeriod.MONTHLY)
        w1 = resolve_period_window(budget, today=date(2026, 6, 1))
        w2 = resolve_period_window(budget, today=date(2026, 6, 30))
        assert period_key(budget, w1) == period_key(budget, w2) == "2026-06-01"

    def test_period_key_changes_across_months(self) -> None:
        budget = _make_budget(period=BudgetPeriod.MONTHLY)
        w_june = resolve_period_window(budget, today=date(2026, 6, 15))
        w_july = resolve_period_window(budget, today=date(2026, 7, 15))
        assert period_key(budget, w_june) != period_key(budget, w_july)


# ══════════════════════════════════════════════════════════════════════════════
# app.alerts.dedup.budget_threshold_scope
# ══════════════════════════════════════════════════════════════════════════════


class TestBudgetThresholdScope:
    def test_scope_differs_by_threshold(self) -> None:
        s1 = budget_threshold_scope(_BUDGET_ID, "2026-06-01", 50.0)
        s2 = budget_threshold_scope(_BUDGET_ID, "2026-06-01", 90.0)
        assert s1 != s2

    def test_scope_differs_by_period(self) -> None:
        s1 = budget_threshold_scope(_BUDGET_ID, "2026-06-01", 50.0)
        s2 = budget_threshold_scope(_BUDGET_ID, "2026-07-01", 50.0)
        assert s1 != s2

    def test_scope_is_deterministic(self) -> None:
        s1 = budget_threshold_scope(_BUDGET_ID, "2026-06-01", 50.0)
        s2 = budget_threshold_scope(_BUDGET_ID, "2026-06-01", 50.0)
        assert s1 == s2


# ══════════════════════════════════════════════════════════════════════════════
# BudgetEvaluationService — spend/forecast/status (no alert firing)
# ══════════════════════════════════════════════════════════════════════════════


def _service_with_totals(totals: list[dict[str, Any]]) -> BudgetEvaluationService:
    session = AsyncMock()
    service = BudgetEvaluationService(session)
    service._cost_records.get_totals_by_org = AsyncMock(return_value=totals)  # type: ignore[method-assign]
    return service


class TestEvaluateBudget:
    @pytest.mark.asyncio
    async def test_current_spend_from_matching_currency_row(self) -> None:
        service = _service_with_totals([{"currency": "USD", "total_cost": Decimal("40.00")}])
        budget = _make_budget(amount=Decimal("100.00"), currency="USD")
        evaluation = await service.evaluate_budget(budget, today=date(2026, 6, 15))
        assert evaluation.current_spend == Decimal("40.00")
        assert evaluation.remaining == Decimal("60.00")
        assert evaluation.percent_used == pytest.approx(40.0)

    @pytest.mark.asyncio
    async def test_no_matching_currency_row_is_zero_spend(self) -> None:
        service = _service_with_totals([{"currency": "EUR", "total_cost": Decimal("40.00")}])
        budget = _make_budget(amount=Decimal("100.00"), currency="USD")
        evaluation = await service.evaluate_budget(budget, today=date(2026, 6, 15))
        assert evaluation.current_spend == Decimal(0)
        assert evaluation.percent_used == 0.0

    @pytest.mark.asyncio
    async def test_project_scope_passes_project_id_filter(self) -> None:
        session = AsyncMock()
        service = BudgetEvaluationService(session)
        mock_totals = AsyncMock(return_value=[])
        service._cost_records.get_totals_by_org = mock_totals  # type: ignore[method-assign]
        budget = _make_budget(scope_type=BudgetScopeType.PROJECT, scope_project_id=_PROJECT_ID)
        await service.evaluate_budget(budget, today=date(2026, 6, 15))
        call_kwargs = mock_totals.call_args.kwargs
        assert call_kwargs["project_id"] == _PROJECT_ID
        assert call_kwargs["provider"] is None
        assert call_kwargs["model"] is None

    @pytest.mark.asyncio
    async def test_provider_scope_passes_provider_filter(self) -> None:
        session = AsyncMock()
        service = BudgetEvaluationService(session)
        mock_totals = AsyncMock(return_value=[])
        service._cost_records.get_totals_by_org = mock_totals  # type: ignore[method-assign]
        budget = _make_budget(scope_type=BudgetScopeType.PROVIDER, scope_provider="openai")
        await service.evaluate_budget(budget, today=date(2026, 6, 15))
        assert mock_totals.call_args.kwargs["provider"] == "openai"

    @pytest.mark.asyncio
    async def test_model_scope_passes_model_filter(self) -> None:
        session = AsyncMock()
        service = BudgetEvaluationService(session)
        mock_totals = AsyncMock(return_value=[])
        service._cost_records.get_totals_by_org = mock_totals  # type: ignore[method-assign]
        budget = _make_budget(scope_type=BudgetScopeType.MODEL, scope_model="gpt-4")
        await service.evaluate_budget(budget, today=date(2026, 6, 15))
        assert mock_totals.call_args.kwargs["model"] == "gpt-4"

    @pytest.mark.asyncio
    async def test_forecast_linear_extrapolation(self) -> None:
        # Monthly budget, June has 30 days; $40 spent after 10 days ->
        # projected = 40 / 10 * 30 = 120.
        service = _service_with_totals([{"currency": "USD", "total_cost": Decimal("40.00")}])
        budget = _make_budget(amount=Decimal("100.00"), period=BudgetPeriod.MONTHLY)
        evaluation = await service.evaluate_budget(budget, today=date(2026, 6, 10))
        assert evaluation.projected_period_spend == Decimal("120.00")

    @pytest.mark.asyncio
    async def test_forecast_zero_days_elapsed_projects_current_spend(self) -> None:
        service = _service_with_totals([{"currency": "USD", "total_cost": Decimal("0")}])
        budget = _make_budget(
            period=BudgetPeriod.CUSTOM,
            custom_period_start=date(2026, 7, 1),
            custom_period_end=date(2026, 7, 31),
        )
        evaluation = await service.evaluate_budget(budget, today=date(2026, 6, 1))
        assert evaluation.projected_period_spend == Decimal(0)

    @pytest.mark.asyncio
    async def test_remaining_daily_allowance(self) -> None:
        # $60 remaining of a $100 monthly budget, 20 days remaining in June -> $3/day
        service = _service_with_totals([{"currency": "USD", "total_cost": Decimal("40.00")}])
        budget = _make_budget(amount=Decimal("100.00"), period=BudgetPeriod.MONTHLY)
        evaluation = await service.evaluate_budget(budget, today=date(2026, 6, 10))
        assert evaluation.remaining_daily_allowance == Decimal("3.00")

    @pytest.mark.asyncio
    async def test_remaining_daily_allowance_zero_when_no_days_remain(self) -> None:
        service = _service_with_totals([{"currency": "USD", "total_cost": Decimal("40.00")}])
        budget = _make_budget(
            amount=Decimal("100.00"),
            period=BudgetPeriod.CUSTOM,
            custom_period_start=date(2026, 6, 1),
            custom_period_end=date(2026, 6, 10),
        )
        evaluation = await service.evaluate_budget(budget, today=date(2026, 7, 1))
        assert evaluation.remaining_daily_allowance == Decimal(0)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("spend", "expected_status"),
        [
            (Decimal("10.00"), "healthy"),
            (Decimal("75.00"), "warning"),
            (Decimal("90.00"), "critical"),
            (Decimal("100.00"), "exceeded"),
            (Decimal("150.00"), "exceeded"),
        ],
    )
    async def test_status_banding(self, spend: Decimal, expected_status: str) -> None:
        service = _service_with_totals([{"currency": "USD", "total_cost": spend}])
        budget = _make_budget(amount=Decimal("100.00"))
        evaluation = await service.evaluate_budget(budget, today=date(2026, 6, 15))
        assert evaluation.status == expected_status

    @pytest.mark.asyncio
    async def test_thresholds_crossed_only_includes_reached_thresholds(self) -> None:
        service = _service_with_totals([{"currency": "USD", "total_cost": Decimal("80.00")}])
        budget = _make_budget(
            amount=Decimal("100.00"), threshold_percentages=[50.0, 75.0, 90.0, 100.0]
        )
        evaluation = await service.evaluate_budget(budget, today=date(2026, 6, 15))
        assert evaluation.thresholds_crossed == [50.0, 75.0]
        assert evaluation.highest_threshold_crossed == 75.0

    @pytest.mark.asyncio
    async def test_no_thresholds_crossed_is_empty(self) -> None:
        service = _service_with_totals([{"currency": "USD", "total_cost": Decimal("10.00")}])
        budget = _make_budget(amount=Decimal("100.00"), threshold_percentages=[50.0, 90.0])
        evaluation = await service.evaluate_budget(budget, today=date(2026, 6, 15))
        assert evaluation.thresholds_crossed == []
        assert evaluation.highest_threshold_crossed is None

    @pytest.mark.asyncio
    async def test_evaluate_organization_evaluates_every_enabled_budget(self) -> None:
        session = AsyncMock()
        service = BudgetEvaluationService(session)
        budgets = [_make_budget(), _make_budget()]
        service._budgets.list_enabled_for_org = AsyncMock(return_value=budgets)  # type: ignore[method-assign]
        service._cost_records.get_totals_by_org = AsyncMock(return_value=[])  # type: ignore[method-assign]
        evaluations = await service.evaluate_organization(_ORG_ID, today=date(2026, 6, 15))
        assert len(evaluations) == 2


# ══════════════════════════════════════════════════════════════════════════════
# BudgetEvaluationService.evaluate_and_alert — firing through AlertService
# ══════════════════════════════════════════════════════════════════════════════


class TestEvaluateAndAlert:
    @pytest.mark.asyncio
    async def test_raises_without_alert_service(self) -> None:
        session = AsyncMock()
        service = BudgetEvaluationService(session)  # no alert_service
        with pytest.raises(RuntimeError):
            await service.evaluate_and_alert(_ORG_ID)

    @pytest.mark.asyncio
    async def test_fires_one_alert_per_threshold_crossed(self) -> None:
        session = AsyncMock()
        mock_alert_service = AsyncMock()
        service = BudgetEvaluationService(session, alert_service=mock_alert_service)
        budget = _make_budget(
            amount=Decimal("100.00"), threshold_percentages=[50.0, 75.0, 90.0, 100.0]
        )
        service._budgets.list_enabled_for_org = AsyncMock(return_value=[budget])  # type: ignore[method-assign]
        service._cost_records.get_totals_by_org = AsyncMock(  # type: ignore[method-assign]
            return_value=[{"currency": "USD", "total_cost": Decimal("80.00")}]
        )
        await service.evaluate_and_alert(_ORG_ID, today=date(2026, 6, 15))
        # 50% and 75% crossed -> two fire() calls
        assert mock_alert_service.fire.await_count == 2
        fired_types = {c.kwargs["alert_type"] for c in mock_alert_service.fire.await_args_list}
        assert fired_types == {AlertType.BUDGET_THRESHOLD}

    @pytest.mark.asyncio
    async def test_exceeded_threshold_fires_budget_exceeded_type(self) -> None:
        session = AsyncMock()
        mock_alert_service = AsyncMock()
        service = BudgetEvaluationService(session, alert_service=mock_alert_service)
        budget = _make_budget(amount=Decimal("100.00"), threshold_percentages=[100.0])
        service._budgets.list_enabled_for_org = AsyncMock(return_value=[budget])  # type: ignore[method-assign]
        service._cost_records.get_totals_by_org = AsyncMock(  # type: ignore[method-assign]
            return_value=[{"currency": "USD", "total_cost": Decimal("120.00")}]
        )
        await service.evaluate_and_alert(_ORG_ID, today=date(2026, 6, 15))
        call = mock_alert_service.fire.await_args_list[0]
        assert call.kwargs["alert_type"] == AlertType.BUDGET_EXCEEDED
        assert call.kwargs["severity"] == AlertSeverity.HIGH

    @pytest.mark.asyncio
    async def test_no_thresholds_crossed_fires_nothing(self) -> None:
        session = AsyncMock()
        mock_alert_service = AsyncMock()
        service = BudgetEvaluationService(session, alert_service=mock_alert_service)
        budget = _make_budget(amount=Decimal("100.00"), threshold_percentages=[90.0])
        service._budgets.list_enabled_for_org = AsyncMock(return_value=[budget])  # type: ignore[method-assign]
        service._cost_records.get_totals_by_org = AsyncMock(  # type: ignore[method-assign]
            return_value=[{"currency": "USD", "total_cost": Decimal("10.00")}]
        )
        await service.evaluate_and_alert(_ORG_ID, today=date(2026, 6, 15))
        mock_alert_service.fire.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_repeated_evaluation_uses_same_dedup_scope(self) -> None:
        """Re-evaluating the same crossed threshold within the same period
        must call fire() with the same dedup-relevant scope both times —
        AlertService.fire() (not exercised here, mocked) is what actually
        folds repeats into one Alert; this test pins that this service
        always derives the same scope for the same (budget, period,
        threshold), which is the precondition for that dedup to work."""
        session = AsyncMock()
        mock_alert_service = AsyncMock()
        service = BudgetEvaluationService(session, alert_service=mock_alert_service)
        budget = _make_budget(amount=Decimal("100.00"), threshold_percentages=[50.0])
        service._budgets.list_enabled_for_org = AsyncMock(return_value=[budget])  # type: ignore[method-assign]
        service._cost_records.get_totals_by_org = AsyncMock(  # type: ignore[method-assign]
            return_value=[{"currency": "USD", "total_cost": Decimal("60.00")}]
        )
        await service.evaluate_and_alert(_ORG_ID, today=date(2026, 6, 15))
        await service.evaluate_and_alert(_ORG_ID, today=date(2026, 6, 15))
        scope_1 = mock_alert_service.fire.await_args_list[0].kwargs["scope"]
        scope_2 = mock_alert_service.fire.await_args_list[1].kwargs["scope"]
        assert scope_1 == scope_2

    @pytest.mark.asyncio
    async def test_alert_fire_failure_does_not_abort_other_budgets(self) -> None:
        session = AsyncMock()
        mock_alert_service = AsyncMock()
        mock_alert_service.fire.side_effect = RuntimeError("boom")
        service = BudgetEvaluationService(session, alert_service=mock_alert_service)
        budget = _make_budget(amount=Decimal("100.00"), threshold_percentages=[50.0])
        service._budgets.list_enabled_for_org = AsyncMock(return_value=[budget, budget])  # type: ignore[method-assign]
        service._cost_records.get_totals_by_org = AsyncMock(  # type: ignore[method-assign]
            return_value=[{"currency": "USD", "total_cost": Decimal("60.00")}]
        )
        # Must not raise even though every fire() call fails.
        evaluations = await service.evaluate_and_alert(_ORG_ID, today=date(2026, 6, 15))
        assert len(evaluations) == 2


# ══════════════════════════════════════════════════════════════════════════════
# BudgetRepository — basic CRUD against a mocked session
# ══════════════════════════════════════════════════════════════════════════════


class TestBudgetRepository:
    @pytest.mark.asyncio
    async def test_list_enabled_for_org_filters_disabled(self) -> None:
        from app.repositories.budget_repository import BudgetRepository

        session = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [_make_budget()]
        session.execute = AsyncMock(return_value=result)
        repo = BudgetRepository(session)
        budgets = await repo.list_enabled_for_org(_ORG_ID)
        assert len(budgets) == 1

    @pytest.mark.asyncio
    async def test_get_for_org_scopes_by_organization(self) -> None:
        from app.repositories.budget_repository import BudgetRepository

        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result)
        repo = BudgetRepository(session)
        budget = await repo.get_for_org(_ORG_ID, _BUDGET_ID)
        assert budget is None


# ══════════════════════════════════════════════════════════════════════════════
# API — /v1/budgets
# ══════════════════════════════════════════════════════════════════════════════


def _override_query_auth(app: Any, *, role: MembershipRole) -> MagicMock:
    from app.api.deps import get_db
    from app.auth.dependencies import get_current_user, get_query_org_membership
    from app.models.membership import Membership
    from app.models.user import User

    mock_user = MagicMock(spec=User)
    mock_user.id = uuid.uuid4()

    async def mock_get_user() -> User:
        return mock_user

    async def mock_get_membership() -> Any:
        m = MagicMock(spec=Membership)
        m.role = role
        return m

    session = AsyncMock()

    async def mock_get_db() -> Any:
        yield session

    app.dependency_overrides[get_current_user] = mock_get_user
    app.dependency_overrides[get_query_org_membership] = mock_get_membership
    app.dependency_overrides[get_db] = mock_get_db
    return session


class TestListBudgetsEndpoint:
    @pytest.mark.asyncio
    async def test_viewer_can_list(self, app: Any) -> None:
        _override_query_auth(app, role=MembershipRole.VIEWER)
        try:
            with patch(
                "app.api.v1.budgets.BudgetRepository.list_for_org",
                new=AsyncMock(return_value=[_make_budget()]),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.get("/v1/budgets", params={"organization_id": str(_ORG_ID)})
            assert resp.status_code == 200
            body = resp.json()
            assert body["total"] == 1
            assert body["budgets"][0]["amount"] == "100.00"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_unauthenticated_is_401(self, app: Any) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/v1/budgets", params={"organization_id": str(_ORG_ID)})
        assert resp.status_code in (401, 403)


class TestCreateBudgetEndpoint:
    @pytest.mark.asyncio
    async def test_member_can_create(self, app: Any) -> None:
        _override_query_auth(app, role=MembershipRole.MEMBER)
        try:
            created = _make_budget()
            with patch(
                "app.api.v1.budgets.BudgetRepository.create",
                new=AsyncMock(return_value=created),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(
                        "/v1/budgets",
                        params={"organization_id": str(_ORG_ID)},
                        json={
                            "name": "Monthly Org Budget",
                            "scope_type": "organization",
                            "amount": "500.00",
                            "currency": "USD",
                            "period": "monthly",
                            "threshold_percentages": [50, 90, 100],
                        },
                    )
            assert resp.status_code == 201
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_viewer_cannot_create(self, app: Any) -> None:
        _override_query_auth(app, role=MembershipRole.VIEWER)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.post(
                    "/v1/budgets",
                    params={"organization_id": str(_ORG_ID)},
                    json={
                        "name": "Monthly Org Budget",
                        "scope_type": "organization",
                        "amount": "500.00",
                        "period": "monthly",
                    },
                )
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_project_scope_without_project_id_is_422(self, app: Any) -> None:
        _override_query_auth(app, role=MembershipRole.MEMBER)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.post(
                    "/v1/budgets",
                    params={"organization_id": str(_ORG_ID)},
                    json={
                        "name": "Project Budget",
                        "scope_type": "project",
                        "amount": "500.00",
                        "period": "monthly",
                    },
                )
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_negative_amount_is_422(self, app: Any) -> None:
        _override_query_auth(app, role=MembershipRole.MEMBER)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.post(
                    "/v1/budgets",
                    params={"organization_id": str(_ORG_ID)},
                    json={
                        "name": "Bad Budget",
                        "scope_type": "organization",
                        "amount": "-10.00",
                        "period": "monthly",
                    },
                )
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.clear()


class TestUpdateBudgetEndpoint:
    @pytest.mark.asyncio
    async def test_member_can_rename(self, app: Any) -> None:
        _override_query_auth(app, role=MembershipRole.MEMBER)
        try:
            existing = _make_budget()
            updated = _make_budget()
            updated.name = "Renamed"
            with (
                patch(
                    "app.api.v1.budgets.BudgetRepository.get_for_org",
                    new=AsyncMock(return_value=existing),
                ),
                patch(
                    "app.api.v1.budgets.BudgetRepository.update",
                    new=AsyncMock(return_value=updated),
                ) as update_mock,
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.patch(
                        f"/v1/budgets/{_BUDGET_ID}",
                        params={"organization_id": str(_ORG_ID)},
                        json={"name": "Renamed"},
                    )
            assert resp.status_code == 200
            assert resp.json()["name"] == "Renamed"
            update_mock.assert_awaited_once()
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_unknown_budget_is_404(self, app: Any) -> None:
        _override_query_auth(app, role=MembershipRole.MEMBER)
        try:
            with patch(
                "app.api.v1.budgets.BudgetRepository.get_for_org",
                new=AsyncMock(return_value=None),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.patch(
                        f"/v1/budgets/{_BUDGET_ID}",
                        params={"organization_id": str(_ORG_ID)},
                        json={"name": "Renamed"},
                    )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()


class TestDeleteBudgetEndpoint:
    @pytest.mark.asyncio
    async def test_member_can_delete(self, app: Any) -> None:
        _override_query_auth(app, role=MembershipRole.MEMBER)
        try:
            existing = _make_budget()
            with (
                patch(
                    "app.api.v1.budgets.BudgetRepository.get_for_org",
                    new=AsyncMock(return_value=existing),
                ),
                patch(
                    "app.api.v1.budgets.BudgetRepository.soft_delete",
                    new=AsyncMock(return_value=existing),
                ) as delete_mock,
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.delete(
                        f"/v1/budgets/{_BUDGET_ID}", params={"organization_id": str(_ORG_ID)}
                    )
            assert resp.status_code == 204
            delete_mock.assert_awaited_once()
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_viewer_cannot_delete(self, app: Any) -> None:
        _override_query_auth(app, role=MembershipRole.VIEWER)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.delete(
                    f"/v1/budgets/{_BUDGET_ID}", params={"organization_id": str(_ORG_ID)}
                )
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()


class TestBudgetStatusEndpoint:
    @pytest.mark.asyncio
    async def test_returns_derived_status(self, app: Any) -> None:
        _override_query_auth(app, role=MembershipRole.VIEWER)
        try:
            existing = _make_budget(amount=Decimal("100.00"))
            with (
                patch(
                    "app.api.v1.budgets.BudgetRepository.get_for_org",
                    new=AsyncMock(return_value=existing),
                ),
                patch(
                    "app.budgets.service.UsageCostRecordRepository.get_totals_by_org",
                    new=AsyncMock(return_value=[{"currency": "USD", "total_cost": Decimal("50")}]),
                ),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.get(
                        f"/v1/budgets/{_BUDGET_ID}/status",
                        params={"organization_id": str(_ORG_ID)},
                    )
            assert resp.status_code == 200
            body = resp.json()
            assert body["current_spend"] == "50"
            assert body["status"] == "healthy"
        finally:
            app.dependency_overrides.clear()


# ══════════════════════════════════════════════════════════════════════════════
# API — GET /v1/dashboard/budget-summary
# ══════════════════════════════════════════════════════════════════════════════


class TestBudgetSummaryEndpoint:
    @pytest.mark.asyncio
    async def test_returns_summary_with_alert_counts(self, app: Any) -> None:
        _override_query_auth(app, role=MembershipRole.VIEWER)
        try:
            budget = _make_budget(amount=Decimal("100.00"))
            with (
                patch(
                    "app.budgets.service.BudgetRepository.list_enabled_for_org",
                    new=AsyncMock(return_value=[budget]),
                ),
                patch(
                    "app.budgets.service.UsageCostRecordRepository.get_totals_by_org",
                    new=AsyncMock(return_value=[{"currency": "USD", "total_cost": Decimal("40")}]),
                ),
                patch(
                    "app.api.v1.dashboard.AlertRepository.list_for_org",
                    new=AsyncMock(return_value=[]),
                ),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.get(
                        "/v1/dashboard/budget-summary",
                        params={"organization_id": str(_ORG_ID)},
                    )
            assert resp.status_code == 200
            body = resp.json()
            assert body["active_alert_count"] == 0
            assert body["critical_alert_count"] == 0
            assert len(body["budgets"]) == 1
            assert body["budgets"][0]["current_spend"] == "40"
            assert "projected_eom_spend" in body
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_unauthenticated_is_401(self, app: Any) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get(
                "/v1/dashboard/budget-summary", params={"organization_id": str(_ORG_ID)}
            )
        assert resp.status_code in (401, 403)


# ══════════════════════════════════════════════════════════════════════════════
# UsageSyncScheduler — post-sync budget evaluation hook
# ══════════════════════════════════════════════════════════════════════════════


def _session_factory_for(session: Any) -> Any:
    @asynccontextmanager
    async def _ctx() -> Any:
        yield session

    factory = MagicMock()
    factory.side_effect = lambda: _ctx()
    return factory


class TestSchedulerBudgetEvaluationHook:
    @pytest.mark.asyncio
    async def test_evaluate_budgets_called_when_event_bus_configured(self) -> None:
        from app.models.usage_collection_run import CollectionRunStatus
        from app.services.usage_sync_scheduler import (
            SchedulerJobRecord,
            SchedulerJobStatus,
            UsageSyncScheduler,
        )

        mock_sync_service = AsyncMock()

        def _run(status: CollectionRunStatus) -> Any:
            r = MagicMock()
            r.status = status
            r.events_collected = 0
            return r

        mock_sync_service.sync_all_connections.return_value = [_run(CollectionRunStatus.COMPLETED)]
        mock_event_bus = MagicMock()
        session_factory = _session_factory_for(MagicMock())
        scheduler = UsageSyncScheduler(
            session_factory,
            event_bus=mock_event_bus,
            sync_service_factory=lambda _s: mock_sync_service,
        )

        job = SchedulerJobRecord(
            job_id=uuid.uuid4(),
            organization_id=_ORG_ID,
            status=SchedulerJobStatus.QUEUED,
            queued_at=datetime.now(UTC),
        )
        with patch.object(scheduler, "_evaluate_budgets", new=AsyncMock()) as mock_evaluate:
            await scheduler._run_job(job)
        mock_evaluate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_evaluate_budgets_skipped_without_event_bus(self) -> None:
        from app.models.usage_collection_run import CollectionRunStatus
        from app.services.usage_sync_scheduler import (
            SchedulerJobRecord,
            SchedulerJobStatus,
            UsageSyncScheduler,
        )

        mock_sync_service = AsyncMock()

        def _run(status: CollectionRunStatus) -> Any:
            r = MagicMock()
            r.status = status
            r.events_collected = 0
            return r

        mock_sync_service.sync_all_connections.return_value = [_run(CollectionRunStatus.COMPLETED)]
        session_factory = _session_factory_for(MagicMock())
        scheduler = UsageSyncScheduler(
            session_factory, sync_service_factory=lambda _s: mock_sync_service
        )  # no event_bus

        job = SchedulerJobRecord(
            job_id=uuid.uuid4(),
            organization_id=_ORG_ID,
            status=SchedulerJobStatus.QUEUED,
            queued_at=datetime.now(UTC),
        )
        with patch.object(scheduler, "_evaluate_budgets", new=AsyncMock()) as mock_evaluate:
            await scheduler._run_job(job)
        mock_evaluate.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_evaluate_budgets_failure_does_not_fail_sync_job(self) -> None:
        """A budget-evaluation error must never turn a successful sync into
        a reported job failure."""
        from app.services.usage_sync_scheduler import UsageSyncScheduler

        mock_event_bus = MagicMock()
        session_factory = _session_factory_for(MagicMock())
        scheduler = UsageSyncScheduler(session_factory, event_bus=mock_event_bus)

        with (
            patch("app.services.usage_sync_scheduler.BudgetEvaluationService") as mock_service_cls,
        ):
            mock_service_cls.return_value.evaluate_and_alert = AsyncMock(
                side_effect=RuntimeError("boom")
            )
            logger = MagicMock()
            # Must not raise.
            await scheduler._evaluate_budgets(AsyncMock(), _ORG_ID, mock_event_bus, logger)
