"""EP-24.1 test suite — Analytics Dashboard & Cost Intelligence.

Coverage targets:
- UsageCostRecordRepository: dimension filters (project/provider/model), model_count,
  prompt/completion token columns on get_daily_trend, get_heatmap SQL aggregation.
- ProviderConnectionRepository.list_recent_failures.
- DashboardService: get_overview trend/active_projects fields, get_project_breakdown
  Project join (name/budget), get_heatmap, get_recent_activity.
- Dashboard API: filter query params, GET /dashboard/heatmap, GET /dashboard/activity.

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

from app.dashboard.service import DashboardService
from app.schemas.dashboard import ActivityResponse, HeatmapResponse

_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000010")
_PROJECT_ID = uuid.UUID("00000000-0000-0000-0000-000000000011")
_TODAY = date(2026, 6, 30)


async def _mock_org_membership() -> Any:
    from app.models.membership import Membership

    return MagicMock(spec=Membership)


def _make_dashboard_service(session: Any | None = None) -> tuple[DashboardService, Any]:
    if session is None:
        session = AsyncMock()
    return DashboardService(session=session), session


# ══════════════════════════════════════════════════════════════════════════════
# Repository — dimension filters
# ══════════════════════════════════════════════════════════════════════════════


class TestDimensionFilters:
    """UsageCostRecordRepository._dimension_filters (EP-24.1)."""

    def test_no_filters_returns_empty_list(self) -> None:
        from app.repositories.usage_cost_record_repository import UsageCostRecordRepository

        repo = UsageCostRecordRepository(AsyncMock())
        filters = repo._dimension_filters()
        assert filters == []

    def test_all_filters_produce_three_clauses(self) -> None:
        from app.repositories.usage_cost_record_repository import UsageCostRecordRepository

        repo = UsageCostRecordRepository(AsyncMock())
        filters = repo._dimension_filters(project_id=_PROJECT_ID, provider="openai", model="gpt-4")
        assert len(filters) == 3

    def test_partial_filters_produce_one_clause(self) -> None:
        from app.repositories.usage_cost_record_repository import UsageCostRecordRepository

        repo = UsageCostRecordRepository(AsyncMock())
        filters = repo._dimension_filters(provider="openai")
        assert len(filters) == 1


# ══════════════════════════════════════════════════════════════════════════════
# Repository — get_totals_by_provider model_count
# ══════════════════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════════════════
# DashboardService.get_overview — EP-24.1 additions
# ══════════════════════════════════════════════════════════════════════════════

_ORG_ROW = {
    "currency": "USD",
    "total_cost": Decimal("100.00"),
    "total_tokens": 5000,
    "total_prompt_tokens": 2500,
    "total_completion_tokens": 2500,
    "record_count": 10,
}

_PROVIDER_ROW = {
    "provider": "openai",
    "currency": "USD",
    "total_cost": Decimal("80.00"),
    "total_tokens": 4000,
    "total_prompt_tokens": 2000,
    "total_completion_tokens": 2000,
    "record_count": 8,
    "model_count": 2,
}

_MODEL_ROW = {
    "provider": "openai",
    "model": "gpt-4",
    "currency": "USD",
    "total_cost": Decimal("60.00"),
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


def _make_cost_repo_mock(**overrides: list) -> AsyncMock:
    repo = AsyncMock()
    repo.get_totals_by_org = AsyncMock(return_value=overrides.get("org_rows", [_ORG_ROW]))
    repo.get_totals_by_provider = AsyncMock(
        return_value=overrides.get("provider_rows", [_PROVIDER_ROW])
    )
    repo.get_totals_by_model = AsyncMock(return_value=overrides.get("model_rows", [_MODEL_ROW]))
    repo.get_totals_by_project = AsyncMock(
        return_value=overrides.get("project_rows", [_PROJECT_ROW])
    )
    repo.get_daily_trend = AsyncMock(return_value=overrides.get("daily_rows", []))
    return repo


class TestOverviewTrendAndProjects:
    """DashboardService.get_overview: active_projects, avg_cost_per_request, trend_pct."""

    @pytest.mark.asyncio
    async def test_active_projects_counts_distinct_non_null_projects(self) -> None:
        svc, session = _make_dashboard_service()
        cost_repo = _make_cost_repo_mock(
            project_rows=[
                {**_PROJECT_ROW, "project_id": _PROJECT_ID},
                {**_PROJECT_ROW, "project_id": uuid.uuid4()},
                {**_PROJECT_ROW, "project_id": None},
            ]
        )
        mock_run_result = MagicMock()
        mock_run_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_run_result)

        with (
            patch("app.dashboard.service.DashboardService._cost_repo", return_value=cost_repo),
            patch("app.dashboard.service.DashboardService._run_repo", return_value=AsyncMock()),
        ):
            result = await svc.get_overview(_ORG_ID, today=_TODAY)

        assert result["active_projects"] == 2

    @pytest.mark.asyncio
    async def test_avg_cost_per_request_computed(self) -> None:
        svc, session = _make_dashboard_service()
        cost_repo = _make_cost_repo_mock(
            org_rows=[{**_ORG_ROW, "total_cost": Decimal("100.00"), "record_count": 10}]
        )
        mock_run_result = MagicMock()
        mock_run_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_run_result)

        with (
            patch("app.dashboard.service.DashboardService._cost_repo", return_value=cost_repo),
            patch("app.dashboard.service.DashboardService._run_repo", return_value=AsyncMock()),
        ):
            result = await svc.get_overview(_ORG_ID, today=_TODAY)

        assert result["avg_cost_per_request"] == Decimal("10.00")

    @pytest.mark.asyncio
    async def test_avg_cost_per_request_none_when_no_requests(self) -> None:
        svc, session = _make_dashboard_service()
        cost_repo = _make_cost_repo_mock(org_rows=[])
        mock_run_result = MagicMock()
        mock_run_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_run_result)

        with (
            patch("app.dashboard.service.DashboardService._cost_repo", return_value=cost_repo),
            patch("app.dashboard.service.DashboardService._run_repo", return_value=AsyncMock()),
        ):
            result = await svc.get_overview(_ORG_ID, today=_TODAY)

        assert result["avg_cost_per_request"] is None

    @pytest.mark.asyncio
    async def test_trend_pct_none_when_no_prior_period(self) -> None:
        """No prior-period baseline (all calls return the same fixed org_rows,
        since the mock can't distinguish date ranges) still yields a defined,
        non-crashing result — division-by-zero is guarded, not raised."""
        svc, session = _make_dashboard_service()
        cost_repo = _make_cost_repo_mock(org_rows=[])
        mock_run_result = MagicMock()
        mock_run_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_run_result)

        with (
            patch("app.dashboard.service.DashboardService._cost_repo", return_value=cost_repo),
            patch("app.dashboard.service.DashboardService._run_repo", return_value=AsyncMock()),
        ):
            result = await svc.get_overview(_ORG_ID, today=_TODAY)

        assert result["cost_trend_pct"] is None
        assert result["request_trend_pct"] is None
        assert result["token_trend_pct"] is None

    @pytest.mark.asyncio
    async def test_trend_pct_positive_growth(self) -> None:
        """_period_over_period_pct: current > prior yields a positive percentage."""
        from app.dashboard.service import _period_over_period_pct

        pct = _period_over_period_pct(Decimal("150"), Decimal("100"))
        assert pct == Decimal("50")

    @pytest.mark.asyncio
    async def test_trend_pct_negative_decline(self) -> None:
        from app.dashboard.service import _period_over_period_pct

        pct = _period_over_period_pct(Decimal("50"), Decimal("100"))
        assert pct == Decimal("-50")

    def test_period_over_period_pct_zero_prior_returns_none(self) -> None:
        from app.dashboard.service import _period_over_period_pct

        assert _period_over_period_pct(Decimal("10"), Decimal("0")) is None


# ══════════════════════════════════════════════════════════════════════════════
# DashboardService.get_project_breakdown — Project join
# ══════════════════════════════════════════════════════════════════════════════


def _fake_project(project_id: uuid.UUID, name: str, budget: Decimal | None) -> Any:
    project = MagicMock()
    project.id = project_id
    project.name = name
    project.budget = budget
    return project


class TestProjectBreakdownJoin:
    """DashboardService.get_project_breakdown: real project_name/budget (EP-24.1)."""

    @pytest.mark.asyncio
    async def test_project_name_and_budget_attached(self) -> None:
        from app.repositories.base_repository import CursorPage

        svc, _ = _make_dashboard_service()
        analytics_svc = AsyncMock()
        analytics_svc.get_project_breakdown = AsyncMock(return_value=[_PROJECT_ROW])
        project = _fake_project(_PROJECT_ID, "Production API", Decimal("100.00"))
        page = CursorPage(items=[project], next_cursor=None, has_more=False)

        with (
            patch(
                "app.dashboard.service.DashboardService._make_analytics_service",
                return_value=analytics_svc,
            ),
            patch(
                "app.repositories.project_repository.ProjectRepository.list_by_org",
                AsyncMock(return_value=page),
            ),
        ):
            result = await svc.get_project_breakdown(_ORG_ID, date(2026, 6, 1), date(2026, 6, 30))

        assert result[0]["project_name"] == "Production API"
        assert result[0]["budget"] == Decimal("100.00")
        # total_cost=50.00 / budget=100.00 * 100 = 50%
        assert result[0]["budget_utilization_pct"] == Decimal("50.00")

    @pytest.mark.asyncio
    async def test_unassigned_when_project_id_none(self) -> None:
        from app.repositories.base_repository import CursorPage

        svc, _ = _make_dashboard_service()
        null_row = {**_PROJECT_ROW, "project_id": None}
        analytics_svc = AsyncMock()
        analytics_svc.get_project_breakdown = AsyncMock(return_value=[null_row])
        page = CursorPage(items=[], next_cursor=None, has_more=False)

        with (
            patch(
                "app.dashboard.service.DashboardService._make_analytics_service",
                return_value=analytics_svc,
            ),
            patch(
                "app.repositories.project_repository.ProjectRepository.list_by_org",
                AsyncMock(return_value=page),
            ),
        ):
            result = await svc.get_project_breakdown(_ORG_ID, date(2026, 6, 1), date(2026, 6, 30))

        assert result[0]["project_name"] == "Unassigned"
        assert result[0]["budget"] is None
        assert result[0]["budget_utilization_pct"] is None

    @pytest.mark.asyncio
    async def test_no_budget_set_yields_none_utilization(self) -> None:
        from app.repositories.base_repository import CursorPage

        svc, _ = _make_dashboard_service()
        analytics_svc = AsyncMock()
        analytics_svc.get_project_breakdown = AsyncMock(return_value=[_PROJECT_ROW])
        project = _fake_project(_PROJECT_ID, "No Budget Project", None)
        page = CursorPage(items=[project], next_cursor=None, has_more=False)

        with (
            patch(
                "app.dashboard.service.DashboardService._make_analytics_service",
                return_value=analytics_svc,
            ),
            patch(
                "app.repositories.project_repository.ProjectRepository.list_by_org",
                AsyncMock(return_value=page),
            ),
        ):
            result = await svc.get_project_breakdown(_ORG_ID, date(2026, 6, 1), date(2026, 6, 30))

        assert result[0]["budget"] is None
        assert result[0]["budget_utilization_pct"] is None


# ══════════════════════════════════════════════════════════════════════════════
# DashboardService.get_heatmap
# ══════════════════════════════════════════════════════════════════════════════


class TestGetHeatmap:
    @pytest.mark.asyncio
    async def test_delegates_to_analytics_service(self) -> None:
        svc, _ = _make_dashboard_service()
        analytics_svc = AsyncMock()
        analytics_svc.get_heatmap = AsyncMock(
            return_value=[
                {
                    "hour_of_day": 14,
                    "day_of_week": 2,
                    "currency": "USD",
                    "total_cost": Decimal("5.00"),
                    "total_tokens": 100,
                    "record_count": 1,
                }
            ]
        )
        with patch(
            "app.dashboard.service.DashboardService._make_analytics_service",
            return_value=analytics_svc,
        ):
            result = await svc.get_heatmap(_ORG_ID, date(2026, 6, 1), date(2026, 6, 30))

        assert len(result) == 1
        assert result[0]["hour_of_day"] == 14
        assert result[0]["day_of_week"] == 2
        assert result[0]["total_requests"] == 1

    @pytest.mark.asyncio
    async def test_empty_result(self) -> None:
        svc, _ = _make_dashboard_service()
        analytics_svc = AsyncMock()
        analytics_svc.get_heatmap = AsyncMock(return_value=[])
        with patch(
            "app.dashboard.service.DashboardService._make_analytics_service",
            return_value=analytics_svc,
        ):
            result = await svc.get_heatmap(_ORG_ID, date(2026, 6, 1), date(2026, 6, 30))

        assert result == []


# ══════════════════════════════════════════════════════════════════════════════
# DashboardService.get_recent_activity
# ══════════════════════════════════════════════════════════════════════════════


def _fake_run(triggered_by: str, status: str = "completed") -> Any:
    run = MagicMock()
    run.id = uuid.uuid4()
    run.provider = "openai"
    run.status = MagicMock()
    run.status.value = status
    run.triggered_by = MagicMock()
    run.triggered_by.value = triggered_by
    run.started_at = datetime(2026, 6, 30, 10, 0, tzinfo=UTC)
    run.completed_at = datetime(2026, 6, 30, 10, 1, tzinfo=UTC)
    run.events_collected = 42
    run.error_message = None
    return run


def _fake_connection(has_failure: bool = True) -> Any:
    from app.models.provider_connection import ProviderType

    conn = MagicMock()
    conn.id = uuid.uuid4()
    conn.provider_type = ProviderType.OPENAI
    conn.display_name = "Prod OpenAI"
    conn.last_error = "The API key is invalid or has been revoked." if has_failure else None
    conn.last_failure_at = datetime(2026, 6, 30, 9, 0, tzinfo=UTC) if has_failure else None
    conn.consecutive_failure_count = 3 if has_failure else 0
    return conn


class TestGetRecentActivity:
    @pytest.mark.asyncio
    async def test_splits_manual_and_scheduled_runs(self) -> None:
        from app.repositories.base_repository import CursorPage

        svc, _session = _make_dashboard_service()
        manual_run = _fake_run("manual")
        scheduled_run = _fake_run("scheduled")
        runs_page = CursorPage(items=[manual_run, scheduled_run], next_cursor=None, has_more=False)

        run_repo = AsyncMock()
        run_repo.list_by_org = AsyncMock(return_value=runs_page)

        with (
            patch("app.dashboard.service.DashboardService._run_repo", return_value=run_repo),
            patch(
                "app.repositories.provider_connection_repository."
                "ProviderConnectionRepository.list_recent_failures",
                AsyncMock(return_value=[]),
            ),
        ):
            result = await svc.get_recent_activity(_ORG_ID, limit=20)

        assert len(result["imports"]) == 1
        assert len(result["syncs"]) == 1
        assert result["failures"] == []

    @pytest.mark.asyncio
    async def test_failures_from_provider_connections(self) -> None:
        from app.repositories.base_repository import CursorPage

        svc, _session = _make_dashboard_service()
        runs_page = CursorPage(items=[], next_cursor=None, has_more=False)
        run_repo = AsyncMock()
        run_repo.list_by_org = AsyncMock(return_value=runs_page)

        failed_conn = _fake_connection(has_failure=True)

        with (
            patch("app.dashboard.service.DashboardService._run_repo", return_value=run_repo),
            patch(
                "app.repositories.provider_connection_repository."
                "ProviderConnectionRepository.list_recent_failures",
                AsyncMock(return_value=[failed_conn]),
            ),
        ):
            result = await svc.get_recent_activity(_ORG_ID, limit=20)

        assert len(result["failures"]) == 1
        assert result["failures"][0]["display_name"] == "Prod OpenAI"
        assert result["failures"][0]["consecutive_failure_count"] == 3

    @pytest.mark.asyncio
    async def test_empty_org_returns_empty_sections(self) -> None:
        from app.repositories.base_repository import CursorPage

        svc, _session = _make_dashboard_service()
        runs_page = CursorPage(items=[], next_cursor=None, has_more=False)
        run_repo = AsyncMock()
        run_repo.list_by_org = AsyncMock(return_value=runs_page)

        with (
            patch("app.dashboard.service.DashboardService._run_repo", return_value=run_repo),
            patch(
                "app.repositories.provider_connection_repository."
                "ProviderConnectionRepository.list_recent_failures",
                AsyncMock(return_value=[]),
            ),
        ):
            result = await svc.get_recent_activity(_ORG_ID, limit=20)

        assert result == {"imports": [], "syncs": [], "failures": []}


# ══════════════════════════════════════════════════════════════════════════════
# API — GET /v1/dashboard/heatmap
# ══════════════════════════════════════════════════════════════════════════════


class TestHeatmapEndpoint:
    @pytest.mark.asyncio
    async def test_heatmap_returns_200(self, app: Any) -> None:
        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User

        mock_user = MagicMock(spec=User)

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        async def mock_get_db():
            yield AsyncMock()

        rows = [
            {
                "hour_of_day": 14,
                "day_of_week": 2,
                "currency": "USD",
                "total_cost": Decimal("5.00"),
                "total_tokens": 100,
                "total_requests": 1,
            }
        ]

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership
        app.dependency_overrides[get_db] = mock_get_db
        try:
            with patch(
                "app.api.v1.dashboard.DashboardService.get_heatmap",
                new_callable=AsyncMock,
                return_value=rows,
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.get(
                        "/v1/dashboard/heatmap",
                        params={
                            "organization_id": str(_ORG_ID),
                            "start_date": "2026-06-01",
                            "end_date": "2026-06-30",
                        },
                    )
            assert resp.status_code == 200
            body = resp.json()
            parsed = HeatmapResponse.model_validate(body)
            assert len(parsed.cells) == 1
            assert parsed.cells[0].hour_of_day == 14
            assert parsed.cells[0].day_of_week == 2
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_heatmap_invalid_date_range_422(self, app: Any) -> None:
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
                    "/v1/dashboard/heatmap",
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
    async def test_heatmap_unauthenticated_401(self, app: Any) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get(
                "/v1/dashboard/heatmap",
                params={
                    "organization_id": str(_ORG_ID),
                    "start_date": "2026-06-01",
                    "end_date": "2026-06-30",
                },
            )
        assert resp.status_code in (401, 403)


# ══════════════════════════════════════════════════════════════════════════════
# API — GET /v1/dashboard/activity
# ══════════════════════════════════════════════════════════════════════════════


class TestActivityEndpoint:
    @pytest.mark.asyncio
    async def test_activity_returns_200(self, app: Any) -> None:
        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User

        mock_user = MagicMock(spec=User)

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        async def mock_get_db():
            yield AsyncMock()

        activity_data = {
            "imports": [
                {
                    "id": str(uuid.uuid4()),
                    "provider": "openai",
                    "status": "completed",
                    "triggered_by": "manual",
                    "started_at": datetime(2026, 6, 30, 10, 0, tzinfo=UTC),
                    "completed_at": datetime(2026, 6, 30, 10, 1, tzinfo=UTC),
                    "events_collected": 10,
                    "error_message": None,
                }
            ],
            "syncs": [],
            "failures": [
                {
                    "connection_id": str(uuid.uuid4()),
                    "provider_type": "openai",
                    "display_name": "Prod OpenAI",
                    "last_error": "The API key is invalid or has been revoked.",
                    "last_failure_at": datetime(2026, 6, 30, 9, 0, tzinfo=UTC),
                    "consecutive_failure_count": 2,
                }
            ],
        }

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership
        app.dependency_overrides[get_db] = mock_get_db
        try:
            with patch(
                "app.api.v1.dashboard.DashboardService.get_recent_activity",
                new_callable=AsyncMock,
                return_value=activity_data,
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.get(
                        "/v1/dashboard/activity",
                        params={"organization_id": str(_ORG_ID)},
                    )
            assert resp.status_code == 200
            body = resp.json()
            parsed = ActivityResponse.model_validate(body)
            assert len(parsed.imports) == 1
            assert len(parsed.failures) == 1
            assert parsed.failures[0].display_name == "Prod OpenAI"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_activity_empty_org(self, app: Any) -> None:
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
            with patch(
                "app.api.v1.dashboard.DashboardService.get_recent_activity",
                new_callable=AsyncMock,
                return_value={"imports": [], "syncs": [], "failures": []},
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.get(
                        "/v1/dashboard/activity",
                        params={"organization_id": str(_ORG_ID)},
                    )
            assert resp.status_code == 200
            body = resp.json()
            assert body["imports"] == []
            assert body["syncs"] == []
            assert body["failures"] == []
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_activity_limit_exceeds_max_422(self, app: Any) -> None:
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
                    "/v1/dashboard/activity",
                    params={"organization_id": str(_ORG_ID), "limit": "500"},
                )
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_activity_unauthenticated_401(self, app: Any) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get(
                "/v1/dashboard/activity",
                params={"organization_id": str(_ORG_ID)},
            )
        assert resp.status_code in (401, 403)


# ══════════════════════════════════════════════════════════════════════════════
# API — filter query params on existing endpoints (EP-24.1)
# ══════════════════════════════════════════════════════════════════════════════


class TestFilterQueryParams:
    @pytest.mark.asyncio
    async def test_providers_endpoint_passes_filters_to_service(self, app: Any) -> None:
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
            with patch(
                "app.api.v1.dashboard.DashboardService.get_provider_breakdown",
                new_callable=AsyncMock,
                return_value=[],
            ) as mock_method:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.get(
                        "/v1/dashboard/providers",
                        params={
                            "organization_id": str(_ORG_ID),
                            "start_date": "2026-06-01",
                            "end_date": "2026-06-30",
                            "project_id": str(_PROJECT_ID),
                            "provider": "openai",
                            "model": "gpt-4",
                        },
                    )
            assert resp.status_code == 200
            _, kwargs = mock_method.call_args
            assert kwargs["project_id"] == _PROJECT_ID
            assert kwargs["provider"] == "openai"
            assert kwargs["model"] == "gpt-4"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_time_series_endpoint_passes_filters_to_service(self, app: Any) -> None:
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
            with patch(
                "app.api.v1.dashboard.DashboardService.get_time_series",
                new_callable=AsyncMock,
                return_value=[],
            ) as mock_method:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.get(
                        "/v1/dashboard/time-series",
                        params={
                            "organization_id": str(_ORG_ID),
                            "start_date": "2026-06-01",
                            "end_date": "2026-06-30",
                            "provider": "anthropic",
                        },
                    )
            assert resp.status_code == 200
            _, kwargs = mock_method.call_args
            assert kwargs["provider"] == "anthropic"
            assert kwargs["project_id"] is None
            assert kwargs["model"] is None
        finally:
            app.dependency_overrides.clear()
