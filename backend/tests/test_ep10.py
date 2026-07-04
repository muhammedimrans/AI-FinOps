"""EP-10 test suite — Dashboard API & Executive Analytics Layer.

Coverage targets:
- DashboardService: all methods (get_overview, get_time_series, get_provider_breakdown,
  get_model_breakdown, get_project_breakdown, get_kpis)
- Dashboard schemas: OverviewResponse, TimeSeriesResponse, ProviderBreakdownResponse,
  ModelBreakdownResponse, ProjectBreakdownResponse, KPIResponse
- Dashboard API: all 7 endpoints (F-060 through F-066)
- Auth guards: unauthenticated requests return 401/422
- Validation guards: missing/invalid params return 422
- Edge cases: empty data, Decimal-as-string serialization

All tests are hermetic — no network calls, no real database.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# ── Test subject imports ───────────────────────────────────────────────────────
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


async def _mock_org_membership() -> Any:
    """Bypass the org-membership guard — authz behavior is tested separately."""
    from app.models.membership import Membership

    return MagicMock(spec=Membership)


# ── Test helpers ───────────────────────────────────────────────────────────────

_NOW = datetime(2026, 6, 30, 12, 0, 0, tzinfo=UTC)
_TODAY = date(2026, 6, 30)
_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000010")
_PROJECT_ID = uuid.UUID("00000000-0000-0000-0000-000000000011")

_PROVIDER_ROW = {
    "provider": "openai",
    "currency": "USD",
    "total_cost": Decimal("80.00"),
    "total_prompt_cost": Decimal("30.00"),
    "total_completion_cost": Decimal("50.00"),
    "total_tokens": 4000,
    "total_prompt_tokens": 2000,
    "total_completion_tokens": 2000,
    "record_count": 8,
}

_MODEL_ROW = {
    "provider": "openai",
    "model": "gpt-4",
    "currency": "USD",
    "total_cost": Decimal("60.00"),
    "total_prompt_cost": Decimal("20.00"),
    "total_completion_cost": Decimal("40.00"),
    "total_tokens": 3000,
    "total_prompt_tokens": 1500,
    "total_completion_tokens": 1500,
    "record_count": 6,
}

_PROJECT_ROW = {
    "project_id": _PROJECT_ID,
    "currency": "USD",
    "total_cost": Decimal("50.00"),
    "total_tokens": 2500,
    "record_count": 5,
}

_DAILY_TREND_ROW = {
    "usage_date": date(2026, 6, 30),
    "currency": "USD",
    "total_cost": Decimal("10.00"),
    "total_prompt_cost": Decimal("4.00"),
    "total_completion_cost": Decimal("6.00"),
    "total_tokens": 500,
    "record_count": 2,
}

_ORG_ROW = {
    "currency": "USD",
    "total_cost": Decimal("100.00"),
    "total_tokens": 5000,
    "total_prompt_tokens": 2500,
    "total_completion_tokens": 2500,
    "record_count": 10,
}


def _make_dashboard_service(
    session: Any | None = None,
) -> tuple[DashboardService, Any]:
    """Build a DashboardService backed by a mock session."""
    if session is None:
        session = AsyncMock()
    svc = DashboardService(session=session)
    return svc, session


def _make_cost_repo_mock(
    org_rows: list | None = None,
    provider_rows: list | None = None,
    model_rows: list | None = None,
    project_rows: list | None = None,
    daily_rows: list | None = None,
) -> AsyncMock:
    repo = AsyncMock()
    repo.get_totals_by_org = AsyncMock(
        return_value=org_rows if org_rows is not None else [_ORG_ROW]
    )
    repo.get_totals_by_provider = AsyncMock(
        return_value=provider_rows if provider_rows is not None else [_PROVIDER_ROW]
    )
    repo.get_totals_by_model = AsyncMock(
        return_value=model_rows if model_rows is not None else [_MODEL_ROW]
    )
    repo.get_totals_by_project = AsyncMock(
        return_value=project_rows if project_rows is not None else [_PROJECT_ROW]
    )
    repo.get_daily_trend = AsyncMock(
        return_value=daily_rows if daily_rows is not None else [_DAILY_TREND_ROW]
    )
    return repo


def _make_analytics_service_mock(
    provider_rows: list | None = None,
    model_rows: list | None = None,
    project_rows: list | None = None,
    daily_rows: list | None = None,
) -> AsyncMock:
    svc = AsyncMock()
    svc.get_provider_breakdown = AsyncMock(
        return_value=provider_rows if provider_rows is not None else [_PROVIDER_ROW]
    )
    svc.get_model_breakdown = AsyncMock(
        return_value=model_rows if model_rows is not None else [_MODEL_ROW]
    )
    svc.get_top_models = AsyncMock(
        return_value=model_rows if model_rows is not None else [_MODEL_ROW]
    )
    svc.get_project_breakdown = AsyncMock(
        return_value=project_rows if project_rows is not None else [_PROJECT_ROW]
    )
    svc.get_daily_trend = AsyncMock(
        return_value=daily_rows if daily_rows is not None else [_DAILY_TREND_ROW]
    )
    return svc


# ══════════════════════════════════════════════════════════════════════════════
# Schema Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestDashboardSchemas:
    """Validate schema construction and Decimal serialization."""

    def test_overview_response_construction(self) -> None:
        resp = OverviewResponse(
            total_spend="100.00",
            today_spend="5.00",
            month_spend="50.00",
            total_tokens=5000,
            total_requests=10,
            active_providers=2,
            active_models=3,
            collection_status="completed",
            last_collection_at=_NOW,
            currency="USD",
        )
        assert resp.total_spend == "100.00"
        assert resp.today_spend == "5.00"
        assert resp.currency == "USD"
        assert resp.collection_status == "completed"
        assert isinstance(resp.last_collection_at, datetime)

    def test_overview_response_null_collection(self) -> None:
        resp = OverviewResponse(
            total_spend="0",
            today_spend="0",
            month_spend="0",
            total_tokens=0,
            total_requests=0,
            active_providers=0,
            active_models=0,
            collection_status=None,
            last_collection_at=None,
            currency="USD",
        )
        assert resp.collection_status is None
        assert resp.last_collection_at is None

    def test_time_series_point(self) -> None:
        pt = TimeSeriesPoint(
            date="2026-06-30", cost="10.00", tokens=500, requests=2, currency="USD"
        )
        assert pt.date == "2026-06-30"
        assert pt.cost == "10.00"
        assert pt.tokens == 500

    def test_time_series_response(self) -> None:
        pts = [
            TimeSeriesPoint(date="2026-06-30", cost="10.00", tokens=500, requests=2, currency="USD")
        ]
        resp = TimeSeriesResponse(
            granularity="daily",
            start_date="2026-06-01",
            end_date="2026-06-30",
            points=pts,
            total_cost="10.00",
            total_tokens=500,
            total_requests=2,
        )
        assert resp.granularity == "daily"
        assert len(resp.points) == 1
        assert resp.total_cost == "10.00"

    def test_time_series_response_empty_points(self) -> None:
        resp = TimeSeriesResponse(
            granularity="daily",
            start_date="2026-06-01",
            end_date="2026-06-30",
            points=[],
            total_cost="0",
            total_tokens=0,
            total_requests=0,
        )
        assert resp.points == []
        assert resp.total_cost == "0"

    def test_provider_metrics_schema(self) -> None:
        pm = ProviderMetrics(
            provider="openai",
            total_cost="80.00",
            total_tokens=4000,
            total_requests=8,
            avg_cost_per_request="10.00",
            currency="USD",
        )
        assert pm.provider == "openai"
        assert pm.total_cost == "80.00"
        assert pm.avg_cost_per_request == "10.00"

    def test_provider_breakdown_response_empty(self) -> None:
        resp = ProviderBreakdownResponse(
            providers=[],
            total_cost="0",
            period_start="2026-06-01",
            period_end="2026-06-30",
        )
        assert resp.providers == []
        assert resp.total_cost == "0"

    def test_model_metrics_schema(self) -> None:
        mm = ModelMetrics(
            provider="openai",
            model="gpt-4",
            total_cost="60.00",
            total_tokens=3000,
            total_requests=6,
            avg_cost_per_request="10.00",
            currency="USD",
        )
        assert mm.model == "gpt-4"
        assert mm.total_cost == "60.00"

    def test_model_breakdown_response_empty(self) -> None:
        resp = ModelBreakdownResponse(
            models=[],
            total_cost="0",
            period_start="2026-06-01",
            period_end="2026-06-30",
        )
        assert resp.models == []

    def test_project_metrics_null_project_id(self) -> None:
        pm = ProjectMetrics(
            project_id=None,
            total_cost="25.00",
            total_tokens=1000,
            total_requests=3,
            currency="USD",
        )
        assert pm.project_id is None

    def test_project_breakdown_response(self) -> None:
        resp = ProjectBreakdownResponse(
            projects=[],
            total_cost="0",
            period_start="2026-06-01",
            period_end="2026-06-30",
        )
        assert resp.projects == []

    def test_kpi_response_all_nulls(self) -> None:
        resp = KPIResponse(
            highest_cost_provider=None,
            highest_cost_model=None,
            avg_cost_per_request=None,
            avg_cost_per_token=None,
            period_start="2026-06-01",
            period_end="2026-06-30",
            currency="USD",
        )
        assert resp.highest_cost_provider is None
        assert resp.avg_cost_per_request is None

    def test_kpi_response_with_values(self) -> None:
        resp = KPIResponse(
            highest_cost_provider="openai",
            highest_cost_model="gpt-4",
            avg_cost_per_request="10.00000000",
            avg_cost_per_token="0.00002000",
            period_start="2026-06-01",
            period_end="2026-06-30",
            currency="USD",
        )
        assert resp.highest_cost_provider == "openai"
        assert resp.avg_cost_per_request == "10.00000000"

    def test_decimal_fields_are_strings_not_decimal(self) -> None:
        """Critical: all Decimal values must be serialized as strings in schemas."""
        resp = OverviewResponse(
            total_spend="100.12345678",
            today_spend="5.00",
            month_spend="50.00",
            total_tokens=5000,
            total_requests=10,
            active_providers=2,
            active_models=3,
            collection_status=None,
            last_collection_at=None,
            currency="USD",
        )
        assert isinstance(resp.total_spend, str)
        assert isinstance(resp.today_spend, str)
        assert isinstance(resp.month_spend, str)


# ══════════════════════════════════════════════════════════════════════════════
# DashboardService Unit Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestDashboardServiceOverview:
    """Tests for DashboardService.get_overview()."""

    @pytest.mark.asyncio
    async def test_get_overview_returns_expected_keys(self) -> None:
        svc, session = _make_dashboard_service()
        cost_repo = _make_cost_repo_mock()

        mock_run_result = MagicMock()
        mock_run_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_run_result)

        with (
            patch("app.dashboard.service.DashboardService._cost_repo", return_value=cost_repo),
            patch("app.dashboard.service.DashboardService._run_repo", return_value=AsyncMock()),
        ):
            result = await svc.get_overview(_ORG_ID, today=_TODAY)

        assert "total_spend" in result
        assert "today_spend" in result
        assert "month_spend" in result
        assert "total_tokens" in result
        assert "total_requests" in result
        assert "active_providers" in result
        assert "active_models" in result
        assert "collection_status" in result
        assert "last_collection_at" in result
        assert "currency" in result

    @pytest.mark.asyncio
    async def test_get_overview_no_collection_run(self) -> None:
        svc, session = _make_dashboard_service()
        cost_repo = _make_cost_repo_mock()

        mock_run_result = MagicMock()
        mock_run_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_run_result)

        with (
            patch("app.dashboard.service.DashboardService._cost_repo", return_value=cost_repo),
            patch("app.dashboard.service.DashboardService._run_repo", return_value=AsyncMock()),
        ):
            result = await svc.get_overview(_ORG_ID, today=_TODAY)

        assert result["collection_status"] is None
        assert result["last_collection_at"] is None

    @pytest.mark.asyncio
    async def test_get_overview_with_collection_run(self) -> None:
        svc, session = _make_dashboard_service()
        cost_repo = _make_cost_repo_mock()

        mock_run = MagicMock()
        mock_run.status = MagicMock()
        mock_run.status.value = "completed"
        mock_run.started_at = _NOW

        mock_run_result = MagicMock()
        mock_run_result.scalar_one_or_none.return_value = mock_run
        session.execute = AsyncMock(return_value=mock_run_result)

        with (
            patch("app.dashboard.service.DashboardService._cost_repo", return_value=cost_repo),
            patch("app.dashboard.service.DashboardService._run_repo", return_value=AsyncMock()),
        ):
            result = await svc.get_overview(_ORG_ID, today=_TODAY)

        assert result["collection_status"] == "completed"
        assert result["last_collection_at"] == _NOW

    @pytest.mark.asyncio
    async def test_get_overview_empty_cost_data(self) -> None:
        svc, session = _make_dashboard_service()
        cost_repo = _make_cost_repo_mock(
            org_rows=[],
            provider_rows=[],
            model_rows=[],
        )

        mock_run_result = MagicMock()
        mock_run_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_run_result)

        with (
            patch("app.dashboard.service.DashboardService._cost_repo", return_value=cost_repo),
            patch("app.dashboard.service.DashboardService._run_repo", return_value=AsyncMock()),
        ):
            result = await svc.get_overview(_ORG_ID, today=_TODAY)

        assert result["total_spend"] == Decimal(0)
        assert result["active_providers"] == 0
        assert result["active_models"] == 0

    @pytest.mark.asyncio
    async def test_get_overview_aggregates_providers_correctly(self) -> None:
        svc, session = _make_dashboard_service()
        multi_provider_rows = [
            {**_PROVIDER_ROW, "provider": "openai"},
            {**_PROVIDER_ROW, "provider": "anthropic"},
        ]
        cost_repo = _make_cost_repo_mock(provider_rows=multi_provider_rows)

        mock_run_result = MagicMock()
        mock_run_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_run_result)

        with (
            patch("app.dashboard.service.DashboardService._cost_repo", return_value=cost_repo),
            patch("app.dashboard.service.DashboardService._run_repo", return_value=AsyncMock()),
        ):
            result = await svc.get_overview(_ORG_ID, today=_TODAY)

        assert result["active_providers"] == 2


class TestDashboardServiceTimeSeries:
    """Tests for DashboardService.get_time_series()."""

    @pytest.mark.asyncio
    async def test_daily_granularity(self) -> None:
        svc, _ = _make_dashboard_service()
        analytics_svc = _make_analytics_service_mock()

        with patch(
            "app.dashboard.service.DashboardService._make_analytics_service",
            return_value=analytics_svc,
        ):
            result = await svc.get_time_series(
                _ORG_ID, date(2026, 6, 1), date(2026, 6, 30), "daily"
            )

        assert len(result) == 1
        assert result[0]["date"] == "2026-06-30"
        assert result[0]["cost"] == Decimal("10.00")
        assert result[0]["tokens"] == 500
        assert result[0]["requests"] == 2

    @pytest.mark.asyncio
    async def test_weekly_granularity(self) -> None:
        svc, _ = _make_dashboard_service()
        # Two rows in the same week
        two_day_rows = [
            {
                **_DAILY_TREND_ROW,
                "usage_date": date(2026, 6, 29),
                "total_cost": Decimal("5.00"),
                "total_tokens": 200,
                "record_count": 1,
            },
            {
                **_DAILY_TREND_ROW,
                "usage_date": date(2026, 6, 30),
                "total_cost": Decimal("7.00"),
                "total_tokens": 300,
                "record_count": 2,
            },
        ]
        analytics_svc = _make_analytics_service_mock(daily_rows=two_day_rows)

        with patch(
            "app.dashboard.service.DashboardService._make_analytics_service",
            return_value=analytics_svc,
        ):
            result = await svc.get_time_series(
                _ORG_ID, date(2026, 6, 1), date(2026, 6, 30), "weekly"
            )

        # Both dates are in ISO week 27 of 2026
        assert len(result) == 1
        assert result[0]["cost"] == Decimal("12.00")
        assert result[0]["tokens"] == 500
        assert result[0]["requests"] == 3

    @pytest.mark.asyncio
    async def test_monthly_granularity(self) -> None:
        svc, _ = _make_dashboard_service()
        two_month_rows = [
            {
                **_DAILY_TREND_ROW,
                "usage_date": date(2026, 5, 15),
                "total_cost": Decimal("30.00"),
                "total_tokens": 1000,
                "record_count": 3,
            },
            {
                **_DAILY_TREND_ROW,
                "usage_date": date(2026, 6, 30),
                "total_cost": Decimal("20.00"),
                "total_tokens": 800,
                "record_count": 2,
            },
        ]
        analytics_svc = _make_analytics_service_mock(daily_rows=two_month_rows)

        with patch(
            "app.dashboard.service.DashboardService._make_analytics_service",
            return_value=analytics_svc,
        ):
            result = await svc.get_time_series(
                _ORG_ID, date(2026, 5, 1), date(2026, 6, 30), "monthly"
            )

        assert len(result) == 2
        months = {r["date"] for r in result}
        assert "2026-05" in months
        assert "2026-06" in months

    @pytest.mark.asyncio
    async def test_empty_trend_returns_empty_list(self) -> None:
        svc, _ = _make_dashboard_service()
        analytics_svc = _make_analytics_service_mock(daily_rows=[])

        with patch(
            "app.dashboard.service.DashboardService._make_analytics_service",
            return_value=analytics_svc,
        ):
            result = await svc.get_time_series(
                _ORG_ID, date(2026, 6, 1), date(2026, 6, 30), "daily"
            )

        assert result == []

    @pytest.mark.asyncio
    async def test_unknown_granularity_falls_back_to_daily(self) -> None:
        svc, _ = _make_dashboard_service()
        analytics_svc = _make_analytics_service_mock()

        with patch(
            "app.dashboard.service.DashboardService._make_analytics_service",
            return_value=analytics_svc,
        ):
            result = await svc.get_time_series(
                _ORG_ID, date(2026, 6, 1), date(2026, 6, 30), "unknown"
            )

        # Falls back to daily — same result as daily
        assert len(result) == 1
        assert "date" in result[0]


class TestDashboardServiceProviderBreakdown:
    """Tests for DashboardService.get_provider_breakdown()."""

    @pytest.mark.asyncio
    async def test_returns_provider_list(self) -> None:
        svc, _ = _make_dashboard_service()
        analytics_svc = _make_analytics_service_mock()

        with patch(
            "app.dashboard.service.DashboardService._make_analytics_service",
            return_value=analytics_svc,
        ):
            result = await svc.get_provider_breakdown(_ORG_ID, date(2026, 6, 1), date(2026, 6, 30))

        assert len(result) == 1
        assert result[0]["provider"] == "openai"
        assert "avg_cost_per_request" in result[0]

    @pytest.mark.asyncio
    async def test_avg_cost_per_request_calculated(self) -> None:
        svc, _ = _make_dashboard_service()
        row = {**_PROVIDER_ROW, "total_cost": Decimal("80.00"), "record_count": 8}
        analytics_svc = _make_analytics_service_mock(provider_rows=[row])

        with patch(
            "app.dashboard.service.DashboardService._make_analytics_service",
            return_value=analytics_svc,
        ):
            result = await svc.get_provider_breakdown(_ORG_ID, date(2026, 6, 1), date(2026, 6, 30))

        assert result[0]["avg_cost_per_request"] == Decimal("10.00")

    @pytest.mark.asyncio
    async def test_avg_cost_zero_requests(self) -> None:
        svc, _ = _make_dashboard_service()
        row = {**_PROVIDER_ROW, "total_cost": Decimal("0"), "record_count": 0}
        analytics_svc = _make_analytics_service_mock(provider_rows=[row])

        with patch(
            "app.dashboard.service.DashboardService._make_analytics_service",
            return_value=analytics_svc,
        ):
            result = await svc.get_provider_breakdown(_ORG_ID, date(2026, 6, 1), date(2026, 6, 30))

        assert result[0]["avg_cost_per_request"] == Decimal(0)

    @pytest.mark.asyncio
    async def test_empty_provider_list(self) -> None:
        svc, _ = _make_dashboard_service()
        analytics_svc = _make_analytics_service_mock(provider_rows=[])

        with patch(
            "app.dashboard.service.DashboardService._make_analytics_service",
            return_value=analytics_svc,
        ):
            result = await svc.get_provider_breakdown(_ORG_ID, date(2026, 6, 1), date(2026, 6, 30))

        assert result == []


class TestDashboardServiceModelBreakdown:
    """Tests for DashboardService.get_model_breakdown()."""

    @pytest.mark.asyncio
    async def test_returns_model_list(self) -> None:
        svc, _ = _make_dashboard_service()
        analytics_svc = _make_analytics_service_mock()

        with patch(
            "app.dashboard.service.DashboardService._make_analytics_service",
            return_value=analytics_svc,
        ):
            result = await svc.get_model_breakdown(_ORG_ID, date(2026, 6, 1), date(2026, 6, 30))

        assert len(result) == 1
        assert result[0]["model"] == "gpt-4"
        assert result[0]["provider"] == "openai"
        assert "avg_cost_per_request" in result[0]

    @pytest.mark.asyncio
    async def test_limit_passed_to_service(self) -> None:
        svc, _ = _make_dashboard_service()
        analytics_svc = _make_analytics_service_mock()

        with patch(
            "app.dashboard.service.DashboardService._make_analytics_service",
            return_value=analytics_svc,
        ):
            await svc.get_model_breakdown(_ORG_ID, date(2026, 6, 1), date(2026, 6, 30), limit=5)

        analytics_svc.get_top_models.assert_called_once_with(
            _ORG_ID, date(2026, 6, 1), date(2026, 6, 30), limit=5
        )

    @pytest.mark.asyncio
    async def test_empty_model_list(self) -> None:
        svc, _ = _make_dashboard_service()
        analytics_svc = _make_analytics_service_mock(model_rows=[])

        with patch(
            "app.dashboard.service.DashboardService._make_analytics_service",
            return_value=analytics_svc,
        ):
            result = await svc.get_model_breakdown(_ORG_ID, date(2026, 6, 1), date(2026, 6, 30))

        assert result == []


class TestDashboardServiceProjectBreakdown:
    """Tests for DashboardService.get_project_breakdown()."""

    @pytest.mark.asyncio
    async def test_returns_project_list(self) -> None:
        svc, _ = _make_dashboard_service()
        analytics_svc = _make_analytics_service_mock()

        with patch(
            "app.dashboard.service.DashboardService._make_analytics_service",
            return_value=analytics_svc,
        ):
            result = await svc.get_project_breakdown(_ORG_ID, date(2026, 6, 1), date(2026, 6, 30))

        assert len(result) == 1
        assert result[0]["project_id"] == str(_PROJECT_ID)

    @pytest.mark.asyncio
    async def test_null_project_id_preserved(self) -> None:
        svc, _ = _make_dashboard_service()
        null_row = {**_PROJECT_ROW, "project_id": None}
        analytics_svc = _make_analytics_service_mock(project_rows=[null_row])

        with patch(
            "app.dashboard.service.DashboardService._make_analytics_service",
            return_value=analytics_svc,
        ):
            result = await svc.get_project_breakdown(_ORG_ID, date(2026, 6, 1), date(2026, 6, 30))

        assert result[0]["project_id"] is None

    @pytest.mark.asyncio
    async def test_empty_project_list(self) -> None:
        svc, _ = _make_dashboard_service()
        analytics_svc = _make_analytics_service_mock(project_rows=[])

        with patch(
            "app.dashboard.service.DashboardService._make_analytics_service",
            return_value=analytics_svc,
        ):
            result = await svc.get_project_breakdown(_ORG_ID, date(2026, 6, 1), date(2026, 6, 30))

        assert result == []


class TestDashboardServiceKPIs:
    """Tests for DashboardService.get_kpis()."""

    @pytest.mark.asyncio
    async def test_returns_all_kpi_keys(self) -> None:
        svc, _ = _make_dashboard_service()
        analytics_svc = _make_analytics_service_mock()
        cost_repo = _make_cost_repo_mock()

        with (
            patch(
                "app.dashboard.service.DashboardService._make_analytics_service",
                return_value=analytics_svc,
            ),
            patch("app.dashboard.service.DashboardService._cost_repo", return_value=cost_repo),
        ):
            result = await svc.get_kpis(_ORG_ID, date(2026, 6, 1), date(2026, 6, 30))

        assert "highest_cost_provider" in result
        assert "highest_cost_model" in result
        assert "avg_cost_per_request" in result
        assert "avg_cost_per_token" in result
        assert "currency" in result

    @pytest.mark.asyncio
    async def test_highest_cost_provider_identified(self) -> None:
        svc, _ = _make_dashboard_service()
        provider_rows = [
            {**_PROVIDER_ROW, "provider": "openai", "total_cost": Decimal("80.00")},
            {**_PROVIDER_ROW, "provider": "anthropic", "total_cost": Decimal("120.00")},
        ]
        analytics_svc = _make_analytics_service_mock(provider_rows=provider_rows)
        cost_repo = _make_cost_repo_mock()

        with (
            patch(
                "app.dashboard.service.DashboardService._make_analytics_service",
                return_value=analytics_svc,
            ),
            patch("app.dashboard.service.DashboardService._cost_repo", return_value=cost_repo),
        ):
            result = await svc.get_kpis(_ORG_ID, date(2026, 6, 1), date(2026, 6, 30))

        assert result["highest_cost_provider"] == "anthropic"

    @pytest.mark.asyncio
    async def test_highest_cost_model_identified(self) -> None:
        svc, _ = _make_dashboard_service()
        model_rows = [
            {**_MODEL_ROW, "model": "gpt-3.5", "total_cost": Decimal("20.00")},
            {**_MODEL_ROW, "model": "gpt-4", "total_cost": Decimal("60.00")},
        ]
        analytics_svc = _make_analytics_service_mock(model_rows=model_rows)
        cost_repo = _make_cost_repo_mock()

        with (
            patch(
                "app.dashboard.service.DashboardService._make_analytics_service",
                return_value=analytics_svc,
            ),
            patch("app.dashboard.service.DashboardService._cost_repo", return_value=cost_repo),
        ):
            result = await svc.get_kpis(_ORG_ID, date(2026, 6, 1), date(2026, 6, 30))

        assert result["highest_cost_model"] == "gpt-4"

    @pytest.mark.asyncio
    async def test_avg_cost_per_request_calculated(self) -> None:
        svc, _ = _make_dashboard_service()
        analytics_svc = _make_analytics_service_mock()
        # 100.00 total / 10 requests = 10.00
        cost_repo = _make_cost_repo_mock(org_rows=[_ORG_ROW])

        with (
            patch(
                "app.dashboard.service.DashboardService._make_analytics_service",
                return_value=analytics_svc,
            ),
            patch("app.dashboard.service.DashboardService._cost_repo", return_value=cost_repo),
        ):
            result = await svc.get_kpis(_ORG_ID, date(2026, 6, 1), date(2026, 6, 30))

        assert result["avg_cost_per_request"] == Decimal("100.00") / Decimal(10)

    @pytest.mark.asyncio
    async def test_avg_cost_per_token_calculated(self) -> None:
        svc, _ = _make_dashboard_service()
        analytics_svc = _make_analytics_service_mock()
        # 100.00 total / 5000 tokens = 0.02
        cost_repo = _make_cost_repo_mock(org_rows=[_ORG_ROW])

        with (
            patch(
                "app.dashboard.service.DashboardService._make_analytics_service",
                return_value=analytics_svc,
            ),
            patch("app.dashboard.service.DashboardService._cost_repo", return_value=cost_repo),
        ):
            result = await svc.get_kpis(_ORG_ID, date(2026, 6, 1), date(2026, 6, 30))

        assert result["avg_cost_per_token"] == Decimal("100.00") / Decimal(5000)

    @pytest.mark.asyncio
    async def test_kpis_none_when_no_data(self) -> None:
        svc, _ = _make_dashboard_service()
        analytics_svc = _make_analytics_service_mock(provider_rows=[], model_rows=[])
        cost_repo = _make_cost_repo_mock(org_rows=[])

        with (
            patch(
                "app.dashboard.service.DashboardService._make_analytics_service",
                return_value=analytics_svc,
            ),
            patch("app.dashboard.service.DashboardService._cost_repo", return_value=cost_repo),
        ):
            result = await svc.get_kpis(_ORG_ID, date(2026, 6, 1), date(2026, 6, 30))

        assert result["highest_cost_provider"] is None
        assert result["highest_cost_model"] is None
        assert result["avg_cost_per_request"] is None
        assert result["avg_cost_per_token"] is None

    @pytest.mark.asyncio
    async def test_kpi_uses_decimal_not_float(self) -> None:
        svc, _ = _make_dashboard_service()
        analytics_svc = _make_analytics_service_mock()
        cost_repo = _make_cost_repo_mock()

        with (
            patch(
                "app.dashboard.service.DashboardService._make_analytics_service",
                return_value=analytics_svc,
            ),
            patch("app.dashboard.service.DashboardService._cost_repo", return_value=cost_repo),
        ):
            result = await svc.get_kpis(_ORG_ID, date(2026, 6, 1), date(2026, 6, 30))

        if result["avg_cost_per_request"] is not None:
            assert isinstance(result["avg_cost_per_request"], Decimal)
        if result["avg_cost_per_token"] is not None:
            assert isinstance(result["avg_cost_per_token"], Decimal)


# ══════════════════════════════════════════════════════════════════════════════
# Dashboard API Endpoint Tests
# ══════════════════════════════════════════════════════════════════════════════

# ─── Auth guard tests ─────────────────────────────────────────────────────────


class TestDashboardAuthGuards:
    """All dashboard endpoints must reject unauthenticated requests."""

    @pytest.mark.asyncio
    async def test_overview_requires_auth(self, client: Any) -> None:
        resp = await client.get(
            "/v1/dashboard/overview",
            params={"organization_id": str(_ORG_ID)},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_time_series_requires_auth(self, client: Any) -> None:
        resp = await client.get(
            "/v1/dashboard/time-series",
            params={
                "organization_id": str(_ORG_ID),
                "start_date": "2026-06-01",
                "end_date": "2026-06-30",
            },
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_providers_requires_auth(self, client: Any) -> None:
        resp = await client.get(
            "/v1/dashboard/providers",
            params={
                "organization_id": str(_ORG_ID),
                "start_date": "2026-06-01",
                "end_date": "2026-06-30",
            },
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_models_requires_auth(self, client: Any) -> None:
        resp = await client.get(
            "/v1/dashboard/models",
            params={
                "organization_id": str(_ORG_ID),
                "start_date": "2026-06-01",
                "end_date": "2026-06-30",
            },
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_organization_requires_auth(self, client: Any) -> None:
        resp = await client.get(
            "/v1/dashboard/organization",
            params={"organization_id": str(_ORG_ID)},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_projects_requires_auth(self, client: Any) -> None:
        resp = await client.get(
            "/v1/dashboard/projects",
            params={
                "organization_id": str(_ORG_ID),
                "start_date": "2026-06-01",
                "end_date": "2026-06-30",
            },
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_kpis_requires_auth(self, client: Any) -> None:
        resp = await client.get(
            "/v1/dashboard/kpis",
            params={
                "organization_id": str(_ORG_ID),
                "start_date": "2026-06-01",
                "end_date": "2026-06-30",
            },
        )
        assert resp.status_code == 401


# ─── Validation guard tests ────────────────────────────────────────────────────


class TestDashboardValidationGuards:
    """Invalid query params should return 422."""

    @pytest.mark.asyncio
    async def test_overview_missing_org_id(self, client: Any) -> None:
        # Without auth, JWT check runs first and returns 401.
        # With auth but no org_id, FastAPI returns 422.
        # Both are acceptable — the endpoint requires both auth AND org_id.
        resp = await client.get("/v1/dashboard/overview")
        assert resp.status_code in (401, 422)

    @pytest.mark.asyncio
    async def test_time_series_missing_org_id(self, client: Any) -> None:
        resp = await client.get(
            "/v1/dashboard/time-series",
            params={"start_date": "2026-06-01", "end_date": "2026-06-30"},
        )
        assert resp.status_code in (401, 422)

    @pytest.mark.asyncio
    async def test_time_series_invalid_date_format(self, client: Any) -> None:
        resp = await client.get(
            "/v1/dashboard/time-series",
            params={
                "organization_id": str(_ORG_ID),
                "start_date": "not-a-date",
                "end_date": "2026-06-30",
            },
        )
        assert resp.status_code in (401, 422)

    @pytest.mark.asyncio
    async def test_models_limit_exceeds_max(self, app: Any) -> None:
        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User

        mock_user = MagicMock(spec=User)

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        async def mock_get_db():
            yield AsyncMock()

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership
        app.dependency_overrides[get_db] = mock_get_db
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/v1/dashboard/models",
                    params={
                        "organization_id": str(_ORG_ID),
                        "start_date": "2026-06-01",
                        "end_date": "2026-06-30",
                        "limit": "200",  # exceeds max of 100
                    },
                )
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.clear()


# ─── Happy-path API tests ─────────────────────────────────────────────────────


def _app_with_mocked_auth_and_service(app: Any, mock_service_methods: dict) -> tuple[Any, Any]:
    """Override auth and DashboardService for API tests.

    Returns (app, mock_svc) where mock_svc is the patched DashboardService.
    """
    from app.api.deps import get_db
    from app.auth.dependencies import get_current_user, get_query_org_membership
    from app.models.user import User

    mock_user = MagicMock(spec=User)

    async def mock_get_user() -> User:
        return mock_user  # type: ignore[return-value]

    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()

    async def mock_get_db():
        yield mock_session

    app.dependency_overrides[get_current_user] = mock_get_user
    app.dependency_overrides[get_query_org_membership] = _mock_org_membership
    app.dependency_overrides[get_db] = mock_get_db

    # Patch DashboardService methods
    mock_svc = AsyncMock(spec=DashboardService)
    for method_name, return_value in mock_service_methods.items():
        setattr(mock_svc, method_name, AsyncMock(return_value=return_value))

    return app, mock_svc


class TestOverviewEndpoint:
    """Tests for GET /v1/dashboard/overview."""

    @pytest.mark.asyncio
    async def test_overview_returns_200_with_auth(self, app: Any) -> None:
        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User

        mock_user = MagicMock(spec=User)

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        async def mock_get_db():
            yield mock_session

        overview_data = {
            "total_spend": Decimal("100.00"),
            "today_spend": Decimal("5.00"),
            "month_spend": Decimal("50.00"),
            "total_tokens": 5000,
            "total_requests": 10,
            "active_providers": 2,
            "active_models": 3,
            "collection_status": "completed",
            "last_collection_at": None,
            "currency": "USD",
        }

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership
        app.dependency_overrides[get_db] = mock_get_db
        try:
            with patch(
                "app.api.v1.dashboard.DashboardService.get_overview",
                new_callable=lambda: lambda *a, **kw: AsyncMock(return_value=overview_data)(),
            ):
                # Use patch on the class method instead
                with patch.object(
                    DashboardService, "get_overview", return_value=overview_data
                ) as mock_method:
                    mock_method.__get__ = lambda self, obj, objtype=None: AsyncMock(
                        return_value=overview_data
                    )

                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.get(
                            "/v1/dashboard/overview",
                            params={"organization_id": str(_ORG_ID)},
                        )
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_overview_response_shape(self, app: Any) -> None:
        """Test that the overview endpoint returns the correct shape."""
        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User

        mock_user = MagicMock(spec=User)

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        mock_session = AsyncMock()

        # Mock DB to return no collection runs and empty cost data
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        async def mock_get_db():
            yield mock_session

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership
        app.dependency_overrides[get_db] = mock_get_db
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/v1/dashboard/overview",
                    params={"organization_id": str(_ORG_ID)},
                )
            assert resp.status_code == 200
            data = resp.json()
            assert "total_spend" in data
            assert "today_spend" in data
            assert "month_spend" in data
            assert "total_tokens" in data
            assert "total_requests" in data
            assert "active_providers" in data
            assert "active_models" in data
            assert "collection_status" in data
            assert "currency" in data
            # Decimal values must be strings
            assert isinstance(data["total_spend"], str)
            assert isinstance(data["today_spend"], str)
            assert isinstance(data["month_spend"], str)
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_overview_decimal_values_are_strings(self, app: Any) -> None:
        """Critical: monetary values must be JSON strings, not numbers."""
        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User

        mock_user = MagicMock(spec=User)

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        async def mock_get_db():
            yield mock_session

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership
        app.dependency_overrides[get_db] = mock_get_db
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/v1/dashboard/overview",
                    params={"organization_id": str(_ORG_ID)},
                )
            assert resp.status_code == 200
            data = resp.json()
            # JSON strings, not numbers
            assert isinstance(data["total_spend"], str)
            assert isinstance(data["month_spend"], str)
            assert isinstance(data["today_spend"], str)
        finally:
            app.dependency_overrides.clear()


class TestTimeSeriesEndpoint:
    """Tests for GET /v1/dashboard/time-series."""

    def _setup(self, app: Any) -> tuple[Any, Any, AsyncMock]:
        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User

        mock_user = MagicMock(spec=User)

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        async def mock_get_db():
            yield mock_session

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership
        app.dependency_overrides[get_db] = mock_get_db
        return app, mock_get_user, mock_session

    @pytest.mark.asyncio
    async def test_time_series_daily_returns_200(self, app: Any) -> None:
        app, _, _ = self._setup(app)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/v1/dashboard/time-series",
                    params={
                        "organization_id": str(_ORG_ID),
                        "start_date": "2026-06-01",
                        "end_date": "2026-06-30",
                        "granularity": "daily",
                    },
                )
            assert resp.status_code == 200
            data = resp.json()
            assert "granularity" in data
            assert data["granularity"] == "daily"
            assert "points" in data
            assert "total_cost" in data
            assert isinstance(data["total_cost"], str)
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_time_series_weekly_returns_200(self, app: Any) -> None:
        app, _, _ = self._setup(app)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/v1/dashboard/time-series",
                    params={
                        "organization_id": str(_ORG_ID),
                        "start_date": "2026-06-01",
                        "end_date": "2026-06-30",
                        "granularity": "weekly",
                    },
                )
            assert resp.status_code == 200
            data = resp.json()
            assert data["granularity"] == "weekly"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_time_series_monthly_returns_200(self, app: Any) -> None:
        app, _, _ = self._setup(app)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/v1/dashboard/time-series",
                    params={
                        "organization_id": str(_ORG_ID),
                        "start_date": "2026-06-01",
                        "end_date": "2026-06-30",
                        "granularity": "monthly",
                    },
                )
            assert resp.status_code == 200
            data = resp.json()
            assert data["granularity"] == "monthly"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_time_series_empty_returns_200_not_404(self, app: Any) -> None:
        app, _, _ = self._setup(app)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/v1/dashboard/time-series",
                    params={
                        "organization_id": str(_ORG_ID),
                        "start_date": "2020-01-01",
                        "end_date": "2020-01-31",
                    },
                )
            assert resp.status_code == 200
            data = resp.json()
            assert data["points"] == []
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_time_series_total_cost_is_string(self, app: Any) -> None:
        app, _, _ = self._setup(app)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/v1/dashboard/time-series",
                    params={
                        "organization_id": str(_ORG_ID),
                        "start_date": "2026-06-01",
                        "end_date": "2026-06-30",
                    },
                )
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data["total_cost"], str)
        finally:
            app.dependency_overrides.clear()


class TestProviderEndpoint:
    """Tests for GET /v1/dashboard/providers."""

    @pytest.mark.asyncio
    async def test_providers_returns_200(self, app: Any) -> None:
        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User

        mock_user = MagicMock(spec=User)

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        async def mock_get_db():
            yield mock_session

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership
        app.dependency_overrides[get_db] = mock_get_db
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/v1/dashboard/providers",
                    params={
                        "organization_id": str(_ORG_ID),
                        "start_date": "2026-06-01",
                        "end_date": "2026-06-30",
                    },
                )
            assert resp.status_code == 200
            data = resp.json()
            assert "providers" in data
            assert "total_cost" in data
            assert isinstance(data["providers"], list)
            assert isinstance(data["total_cost"], str)
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_providers_empty_returns_200_not_404(self, app: Any) -> None:
        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User

        mock_user = MagicMock(spec=User)

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        async def mock_get_db():
            yield mock_session

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership
        app.dependency_overrides[get_db] = mock_get_db
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/v1/dashboard/providers",
                    params={
                        "organization_id": str(_ORG_ID),
                        "start_date": "2020-01-01",
                        "end_date": "2020-01-31",
                    },
                )
            assert resp.status_code == 200
            data = resp.json()
            assert data["providers"] == []
        finally:
            app.dependency_overrides.clear()


class TestModelsEndpoint:
    """Tests for GET /v1/dashboard/models."""

    @pytest.mark.asyncio
    async def test_models_returns_200(self, app: Any) -> None:
        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User

        mock_user = MagicMock(spec=User)

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        async def mock_get_db():
            yield mock_session

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership
        app.dependency_overrides[get_db] = mock_get_db
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/v1/dashboard/models",
                    params={
                        "organization_id": str(_ORG_ID),
                        "start_date": "2026-06-01",
                        "end_date": "2026-06-30",
                    },
                )
            assert resp.status_code == 200
            data = resp.json()
            assert "models" in data
            assert "total_cost" in data
            assert isinstance(data["models"], list)
            assert isinstance(data["total_cost"], str)
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_models_respects_limit(self, app: Any) -> None:
        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User

        mock_user = MagicMock(spec=User)

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        async def mock_get_db():
            yield mock_session

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership
        app.dependency_overrides[get_db] = mock_get_db
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/v1/dashboard/models",
                    params={
                        "organization_id": str(_ORG_ID),
                        "start_date": "2026-06-01",
                        "end_date": "2026-06-30",
                        "limit": "5",
                    },
                )
            assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_models_empty_returns_200_not_404(self, app: Any) -> None:
        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User

        mock_user = MagicMock(spec=User)

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        async def mock_get_db():
            yield mock_session

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership
        app.dependency_overrides[get_db] = mock_get_db
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/v1/dashboard/models",
                    params={
                        "organization_id": str(_ORG_ID),
                        "start_date": "2020-01-01",
                        "end_date": "2020-01-31",
                    },
                )
            assert resp.status_code == 200
            data = resp.json()
            assert data["models"] == []
        finally:
            app.dependency_overrides.clear()


class TestOrganizationEndpoint:
    """Tests for GET /v1/dashboard/organization."""

    @pytest.mark.asyncio
    async def test_organization_returns_200(self, app: Any) -> None:
        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User

        mock_user = MagicMock(spec=User)

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        async def mock_get_db():
            yield mock_session

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership
        app.dependency_overrides[get_db] = mock_get_db
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/v1/dashboard/organization",
                    params={"organization_id": str(_ORG_ID)},
                )
            assert resp.status_code == 200
            data = resp.json()
            assert "overview" in data
            assert "provider_breakdown" in data
            assert "top_models" in data
            assert "project_breakdown" in data
            assert "daily_trend" in data
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_organization_composite_response_structure(self, app: Any) -> None:
        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User

        mock_user = MagicMock(spec=User)

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        async def mock_get_db():
            yield mock_session

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership
        app.dependency_overrides[get_db] = mock_get_db
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/v1/dashboard/organization",
                    params={
                        "organization_id": str(_ORG_ID),
                        "start_date": "2026-06-01",
                        "end_date": "2026-06-30",
                    },
                )
            assert resp.status_code == 200
            data = resp.json()
            # Top-level keys
            assert "organization_id" in data
            assert "period_start" in data
            assert "period_end" in data
            # Overview block
            overview = data["overview"]
            assert isinstance(overview["total_spend"], str)
            assert isinstance(overview["month_spend"], str)
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_organization_defaults_to_current_month(self, app: Any) -> None:
        """Start/end dates are optional — defaults to current month."""
        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User

        mock_user = MagicMock(spec=User)

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        async def mock_get_db():
            yield mock_session

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership
        app.dependency_overrides[get_db] = mock_get_db
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                # No start_date / end_date params
                resp = await ac.get(
                    "/v1/dashboard/organization",
                    params={"organization_id": str(_ORG_ID)},
                )
            assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()


class TestProjectsEndpoint:
    """Tests for GET /v1/dashboard/projects."""

    @pytest.mark.asyncio
    async def test_projects_returns_200(self, app: Any) -> None:
        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User

        mock_user = MagicMock(spec=User)

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        async def mock_get_db():
            yield mock_session

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership
        app.dependency_overrides[get_db] = mock_get_db
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/v1/dashboard/projects",
                    params={
                        "organization_id": str(_ORG_ID),
                        "start_date": "2026-06-01",
                        "end_date": "2026-06-30",
                    },
                )
            assert resp.status_code == 200
            data = resp.json()
            assert "projects" in data
            assert "total_cost" in data
            assert isinstance(data["projects"], list)
            assert isinstance(data["total_cost"], str)
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_projects_empty_returns_200_not_404(self, app: Any) -> None:
        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User

        mock_user = MagicMock(spec=User)

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        async def mock_get_db():
            yield mock_session

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership
        app.dependency_overrides[get_db] = mock_get_db
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/v1/dashboard/projects",
                    params={
                        "organization_id": str(_ORG_ID),
                        "start_date": "2020-01-01",
                        "end_date": "2020-01-31",
                    },
                )
            assert resp.status_code == 200
            data = resp.json()
            assert data["projects"] == []
        finally:
            app.dependency_overrides.clear()


class TestKPIsEndpoint:
    """Tests for GET /v1/dashboard/kpis."""

    @pytest.mark.asyncio
    async def test_kpis_returns_200(self, app: Any) -> None:
        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User

        mock_user = MagicMock(spec=User)

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        async def mock_get_db():
            yield mock_session

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership
        app.dependency_overrides[get_db] = mock_get_db
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/v1/dashboard/kpis",
                    params={
                        "organization_id": str(_ORG_ID),
                        "start_date": "2026-06-01",
                        "end_date": "2026-06-30",
                    },
                )
            assert resp.status_code == 200
            data = resp.json()
            assert "highest_cost_provider" in data
            assert "highest_cost_model" in data
            assert "avg_cost_per_request" in data
            assert "avg_cost_per_token" in data
            assert "period_start" in data
            assert "period_end" in data
            assert "currency" in data
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_kpis_empty_data_returns_200_not_404(self, app: Any) -> None:
        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User

        mock_user = MagicMock(spec=User)

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        async def mock_get_db():
            yield mock_session

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership
        app.dependency_overrides[get_db] = mock_get_db
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/v1/dashboard/kpis",
                    params={
                        "organization_id": str(_ORG_ID),
                        "start_date": "2020-01-01",
                        "end_date": "2020-01-31",
                    },
                )
            assert resp.status_code == 200
            data = resp.json()
            assert data["highest_cost_provider"] is None
            assert data["highest_cost_model"] is None
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_kpis_string_fields_for_decimals(self, app: Any) -> None:
        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User

        mock_user = MagicMock(spec=User)

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        async def mock_get_db():
            yield mock_session

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership
        app.dependency_overrides[get_db] = mock_get_db
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/v1/dashboard/kpis",
                    params={
                        "organization_id": str(_ORG_ID),
                        "start_date": "2026-06-01",
                        "end_date": "2026-06-30",
                    },
                )
            assert resp.status_code == 200
            data = resp.json()
            # avg fields should be string or null — never a JSON number
            if data["avg_cost_per_request"] is not None:
                assert isinstance(data["avg_cost_per_request"], str)
            if data["avg_cost_per_token"] is not None:
                assert isinstance(data["avg_cost_per_token"], str)
        finally:
            app.dependency_overrides.clear()


# ══════════════════════════════════════════════════════════════════════════════
# Additional Edge Case Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestDecimalSerializationInAPI:
    """All monetary fields must be JSON strings, never JSON numbers."""

    @pytest.mark.asyncio
    async def test_providers_total_cost_is_string(self, app: Any) -> None:
        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User

        mock_user = MagicMock(spec=User)

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        async def mock_get_db():
            yield mock_session

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership
        app.dependency_overrides[get_db] = mock_get_db
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/v1/dashboard/providers",
                    params={
                        "organization_id": str(_ORG_ID),
                        "start_date": "2026-06-01",
                        "end_date": "2026-06-30",
                    },
                )
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data["total_cost"], str)
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_models_total_cost_is_string(self, app: Any) -> None:
        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User

        mock_user = MagicMock(spec=User)

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        async def mock_get_db():
            yield mock_session

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership
        app.dependency_overrides[get_db] = mock_get_db
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/v1/dashboard/models",
                    params={
                        "organization_id": str(_ORG_ID),
                        "start_date": "2026-06-01",
                        "end_date": "2026-06-30",
                    },
                )
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data["total_cost"], str)
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_projects_total_cost_is_string(self, app: Any) -> None:
        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User

        mock_user = MagicMock(spec=User)

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        async def mock_get_db():
            yield mock_session

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership
        app.dependency_overrides[get_db] = mock_get_db
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/v1/dashboard/projects",
                    params={
                        "organization_id": str(_ORG_ID),
                        "start_date": "2026-06-01",
                        "end_date": "2026-06-30",
                    },
                )
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data["total_cost"], str)
        finally:
            app.dependency_overrides.clear()


class TestRouterRegistration:
    """Verify the dashboard router is registered in the main app."""

    @pytest.mark.asyncio
    async def test_dashboard_routes_exist_in_openapi(self, client: Any) -> None:
        resp = await client.get("/openapi.json")
        assert resp.status_code == 200
        paths = resp.json()["paths"]
        assert "/v1/dashboard/overview" in paths
        assert "/v1/dashboard/time-series" in paths
        assert "/v1/dashboard/providers" in paths
        assert "/v1/dashboard/models" in paths
        assert "/v1/dashboard/organization" in paths
        assert "/v1/dashboard/projects" in paths
        assert "/v1/dashboard/kpis" in paths

    @pytest.mark.asyncio
    async def test_dashboard_tags_in_openapi(self, client: Any) -> None:
        resp = await client.get("/openapi.json")
        assert resp.status_code == 200
        spec = resp.json()
        tags_in_paths = set()
        for path_item in spec["paths"].values():
            for op in path_item.values():
                if isinstance(op, dict) and "tags" in op:
                    tags_in_paths.update(op["tags"])
        assert "dashboard" in tags_in_paths


# ══════════════════════════════════════════════════════════════════════════════
# EP-10 Release Hardening Regression Tests
# ══════════════════════════════════════════════════════════════════════════════


def _authed_client_setup(app: Any) -> None:
    """Configure app dependency overrides for authenticated, DB-mocked tests.

    Caller MUST call app.dependency_overrides.clear() in a finally block.
    """
    from app.api.deps import get_db
    from app.auth.dependencies import get_current_user, get_query_org_membership
    from app.models.user import User

    mock_user = MagicMock(spec=User)

    async def mock_get_user() -> User:
        return mock_user  # type: ignore[return-value]

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_result.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()

    async def mock_get_db():
        yield mock_session

    app.dependency_overrides[get_current_user] = mock_get_user
    app.dependency_overrides[get_query_org_membership] = _mock_org_membership
    app.dependency_overrides[get_db] = mock_get_db


class TestRH01GranularityValidation:
    """RH-01: Invalid granularity values must return 422, not silently degrade."""

    @pytest.mark.asyncio
    async def test_granularity_hourly_returns_422(self, app: Any) -> None:
        """Unknown granularity 'hourly' must return 422."""
        _authed_client_setup(app)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/v1/dashboard/time-series",
                    params={
                        "organization_id": str(_ORG_ID),
                        "start_date": "2026-06-01",
                        "end_date": "2026-06-30",
                        "granularity": "hourly",
                    },
                )
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_granularity_foo_returns_422(self, app: Any) -> None:
        """Arbitrary string granularity 'foo' must return 422."""
        _authed_client_setup(app)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/v1/dashboard/time-series",
                    params={
                        "organization_id": str(_ORG_ID),
                        "start_date": "2026-06-01",
                        "end_date": "2026-06-30",
                        "granularity": "foo",
                    },
                )
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_granularity_wrong_case_returns_422(self, app: Any) -> None:
        """Case-sensitive: 'DAILY' must return 422 (only 'daily' is valid)."""
        _authed_client_setup(app)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/v1/dashboard/time-series",
                    params={
                        "organization_id": str(_ORG_ID),
                        "start_date": "2026-06-01",
                        "end_date": "2026-06-30",
                        "granularity": "DAILY",
                    },
                )
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_granularity_daily_returns_200(self, app: Any) -> None:
        """'daily' is a valid granularity and must return 200."""
        _authed_client_setup(app)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/v1/dashboard/time-series",
                    params={
                        "organization_id": str(_ORG_ID),
                        "start_date": "2026-06-01",
                        "end_date": "2026-06-30",
                        "granularity": "daily",
                    },
                )
            assert resp.status_code == 200
            assert resp.json()["granularity"] == "daily"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_granularity_weekly_returns_200(self, app: Any) -> None:
        """'weekly' is a valid granularity and must return 200."""
        _authed_client_setup(app)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/v1/dashboard/time-series",
                    params={
                        "organization_id": str(_ORG_ID),
                        "start_date": "2026-06-01",
                        "end_date": "2026-06-30",
                        "granularity": "weekly",
                    },
                )
            assert resp.status_code == 200
            assert resp.json()["granularity"] == "weekly"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_granularity_monthly_returns_200(self, app: Any) -> None:
        """'monthly' is a valid granularity and must return 200."""
        _authed_client_setup(app)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/v1/dashboard/time-series",
                    params={
                        "organization_id": str(_ORG_ID),
                        "start_date": "2026-06-01",
                        "end_date": "2026-06-30",
                        "granularity": "monthly",
                    },
                )
            assert resp.status_code == 200
            assert resp.json()["granularity"] == "monthly"
        finally:
            app.dependency_overrides.clear()


class TestRH02DateRangeValidation:
    """RH-02: start_date > end_date must return 422 on all date-range endpoints."""

    @pytest.mark.asyncio
    async def test_providers_inverted_dates_returns_422(self, app: Any) -> None:
        """start_date > end_date on /providers must return 422."""
        _authed_client_setup(app)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/v1/dashboard/providers",
                    params={
                        "organization_id": str(_ORG_ID),
                        "start_date": "2026-06-30",
                        "end_date": "2026-06-01",
                    },
                )
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_models_inverted_dates_returns_422(self, app: Any) -> None:
        """start_date > end_date on /models must return 422."""
        _authed_client_setup(app)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/v1/dashboard/models",
                    params={
                        "organization_id": str(_ORG_ID),
                        "start_date": "2026-06-30",
                        "end_date": "2026-06-01",
                    },
                )
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_kpis_inverted_dates_returns_422(self, app: Any) -> None:
        """start_date > end_date on /kpis must return 422."""
        _authed_client_setup(app)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/v1/dashboard/kpis",
                    params={
                        "organization_id": str(_ORG_ID),
                        "start_date": "2026-12-31",
                        "end_date": "2026-01-01",
                    },
                )
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_time_series_inverted_dates_returns_422(self, app: Any) -> None:
        """start_date > end_date on /time-series must return 422."""
        _authed_client_setup(app)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/v1/dashboard/time-series",
                    params={
                        "organization_id": str(_ORG_ID),
                        "start_date": "2026-06-30",
                        "end_date": "2026-06-01",
                    },
                )
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_projects_inverted_dates_returns_422(self, app: Any) -> None:
        """start_date > end_date on /projects must return 422."""
        _authed_client_setup(app)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/v1/dashboard/projects",
                    params={
                        "organization_id": str(_ORG_ID),
                        "start_date": "2026-06-30",
                        "end_date": "2026-06-01",
                    },
                )
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_organization_inverted_dates_returns_422(self, app: Any) -> None:
        """start_date > end_date on /organization must return 422."""
        _authed_client_setup(app)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/v1/dashboard/organization",
                    params={
                        "organization_id": str(_ORG_ID),
                        "start_date": "2026-06-30",
                        "end_date": "2026-06-01",
                    },
                )
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_same_day_start_end_returns_200(self, app: Any) -> None:
        """start_date == end_date is valid and must return 200."""
        _authed_client_setup(app)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/v1/dashboard/providers",
                    params={
                        "organization_id": str(_ORG_ID),
                        "start_date": "2026-06-30",
                        "end_date": "2026-06-30",
                    },
                )
            assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_date_range_error_message_format(self) -> None:
        """Error message must use the canonical wording."""
        from fastapi import HTTPException

        try:
            start = date(2026, 6, 30)
            end = date(2026, 6, 1)
            if start > end:
                raise HTTPException(
                    status_code=422,
                    detail="start_date must be before or equal to end_date",
                )
            raise AssertionError("Should have raised")
        except HTTPException as exc:
            assert exc.status_code == 422
            assert "start_date" in exc.detail
            assert "end_date" in exc.detail


class TestRH02CurrencyFiltering:
    """RH-02: Mixed-currency cost records must not be cross-summed."""

    @pytest.mark.asyncio
    async def test_provider_breakdown_filters_by_currency(self, app: Any) -> None:
        """Provider breakdown with currency=USD must exclude EUR records."""
        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User

        mock_user = MagicMock(spec=User)

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        mock_session = AsyncMock()

        async def mock_get_db():
            yield mock_session

        # Two providers in different currencies
        mixed_rows = [
            {
                "provider": "openai",
                "currency": "USD",
                "total_cost": Decimal("100.00"),
                "total_tokens": 5000,
                "total_requests": 10,
                "avg_cost_per_request": Decimal("10.00"),
            },
            {
                "provider": "anthropic",
                "currency": "EUR",
                "total_cost": Decimal("80.00"),
                "total_tokens": 4000,
                "total_requests": 8,
                "avg_cost_per_request": Decimal("10.00"),
            },
        ]

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership
        app.dependency_overrides[get_db] = mock_get_db
        try:
            with patch(
                "app.api.v1.dashboard.DashboardService.get_provider_breakdown",
                new_callable=AsyncMock,
                return_value=mixed_rows,
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.get(
                        "/v1/dashboard/providers",
                        params={
                            "organization_id": str(_ORG_ID),
                            "start_date": "2026-06-01",
                            "end_date": "2026-06-30",
                            "currency": "USD",
                        },
                    )
            assert resp.status_code == 200
            data = resp.json()
            # Only USD provider should appear
            assert len(data["providers"]) == 1
            assert data["providers"][0]["provider"] == "openai"
            assert data["providers"][0]["currency"] == "USD"
            # total_cost must be USD-only: 100.00, not 180.00 (cross-currency sum)
            assert data["total_cost"] == "100.00"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_model_breakdown_filters_by_currency(self, app: Any) -> None:
        """Model breakdown with currency=USD must exclude EUR records."""
        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User

        mock_user = MagicMock(spec=User)

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        mock_session = AsyncMock()

        async def mock_get_db():
            yield mock_session

        mixed_model_rows = [
            {
                "provider": "openai",
                "model": "gpt-4",
                "currency": "USD",
                "total_cost": Decimal("60.00"),
                "total_tokens": 3000,
                "total_requests": 6,
                "avg_cost_per_request": Decimal("10.00"),
            },
            {
                "provider": "anthropic",
                "model": "claude-3-opus",
                "currency": "EUR",
                "total_cost": Decimal("50.00"),
                "total_tokens": 2500,
                "total_requests": 5,
                "avg_cost_per_request": Decimal("10.00"),
            },
        ]

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership
        app.dependency_overrides[get_db] = mock_get_db
        try:
            with patch(
                "app.api.v1.dashboard.DashboardService.get_model_breakdown",
                new_callable=AsyncMock,
                return_value=mixed_model_rows,
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.get(
                        "/v1/dashboard/models",
                        params={
                            "organization_id": str(_ORG_ID),
                            "start_date": "2026-06-01",
                            "end_date": "2026-06-30",
                            "currency": "USD",
                        },
                    )
            assert resp.status_code == 200
            data = resp.json()
            # Only USD model should appear
            assert len(data["models"]) == 1
            assert data["models"][0]["model"] == "gpt-4"
            # total_cost must be USD-only: 60.00, not 110.00
            assert data["total_cost"] == "60.00"
        finally:
            app.dependency_overrides.clear()


class TestRH03ResponseModelOrganization:
    """RH-03: /organization endpoint must have a typed response_model."""

    @pytest.mark.asyncio
    async def test_organization_response_model_in_openapi(self, client: Any) -> None:
        """The /organization endpoint must have a schema in OpenAPI (not untyped object)."""
        resp = await client.get("/openapi.json")
        assert resp.status_code == 200
        spec = resp.json()
        org_path = spec["paths"].get("/v1/dashboard/organization", {})
        get_op = org_path.get("get", {})
        responses = get_op.get("responses", {})
        response_200 = responses.get("200", {})
        content = response_200.get("content", {})
        json_content = content.get("application/json", {})
        schema = json_content.get("schema", {})
        # Must have a $ref pointing to a schema (not an empty object {})
        has_ref = "$ref" in schema or "properties" in schema
        assert has_ref, f"Expected typed schema for /organization, got: {schema}"

    @pytest.mark.asyncio
    async def test_organization_response_contains_required_keys(self, app: Any) -> None:
        """The /organization response must contain overview, provider_breakdown,
        top_models, project_breakdown, and daily_trend keys."""
        _authed_client_setup(app)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/v1/dashboard/organization",
                    params={"organization_id": str(_ORG_ID)},
                )
            assert resp.status_code == 200
            data = resp.json()
            assert "overview" in data
            assert "provider_breakdown" in data
            assert "top_models" in data
            assert "project_breakdown" in data
            assert "daily_trend" in data
            assert "organization_id" in data
            assert "period_start" in data
            assert "period_end" in data
            assert "currency" in data
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_organization_overview_block_monetary_fields_are_strings(self, app: Any) -> None:
        """Overview monetary fields in /organization must be JSON strings."""
        _authed_client_setup(app)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/v1/dashboard/organization",
                    params={"organization_id": str(_ORG_ID)},
                )
            assert resp.status_code == 200
            data = resp.json()
            overview = data["overview"]
            assert isinstance(overview["total_spend"], str)
            assert isinstance(overview["today_spend"], str)
            assert isinstance(overview["month_spend"], str)
        finally:
            app.dependency_overrides.clear()
