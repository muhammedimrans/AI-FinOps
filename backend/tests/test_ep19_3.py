"""EP-19.3 test suite — Alert Rule Engine & Notification Persistence.

Coverage:
  - app.alerts.conditions: compare(), percent_increase(), rolling_average(),
    evaluate() (AND/OR/NOT composition)
  - app.alerts.rule_engine: RuleEngine.evaluate_type()
  - app.alerts.dedup: build_dedup_key() + scope helpers
  - app.alerts.suppression: is_suppressed() (organization/alert_type/provider)
  - app.alerts.preferences: get_or_default(), is_within_quiet_hours(),
    should_surface(), minute_of_day()
  - app.alerts.dispatcher: AlertService.fire() (create / dedup / suppress paths)
  - app/api/v1/alerts.py: acknowledge/resolve/dismiss/reopen lifecycle,
    organization isolation, list/search filtering
  - Organization isolation: an alert belonging to another org is never
    returned or mutated by ID guessing (404, not 200/403 — no leakage of
    existence).

All tests are hermetic — no network calls, no real database (AsyncMock
session), matching the pattern already used across this suite
(tests/test_ep19_1.py, tests/test_api_keys.py, tests/test_ep09.py).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, time
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.alerts.conditions import (
    CompositeCondition,
    LeafCondition,
    LogicalOperator,
    compare,
    evaluate,
    percent_increase,
    rolling_average,
)
from app.alerts.dedup import api_key_scope, budget_scope, build_dedup_key, membership_scope
from app.alerts.dispatcher import AlertService
from app.alerts.preferences import (
    get_or_default,
    is_within_quiet_hours,
    minute_of_day,
    should_surface,
)
from app.alerts.rule_engine import RuleEngine
from app.alerts.suppression import is_suppressed
from app.models.alert import (
    Alert,
    AlertOperator,
    AlertPreference,
    AlertRule,
    AlertSeverity,
    AlertStatus,
    AlertSuppression,
    AlertType,
    SuppressionScope,
)

_ORG_ID = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
_OTHER_ORG_ID = uuid.UUID("00000000-0000-0000-0000-0000000000a2")
_USER_ID = uuid.UUID("00000000-0000-0000-0000-0000000000b1")
_NOW = datetime(2026, 7, 3, 12, 0, 0, tzinfo=UTC)


# ── conditions.py ────────────────────────────────────────────────────────────


class TestCompare:
    @pytest.mark.parametrize(
        ("operator", "current", "threshold", "expected"),
        [
            (AlertOperator.GT, 10, 5, True),
            (AlertOperator.GT, 5, 10, False),
            (AlertOperator.LT, 5, 10, True),
            (AlertOperator.LT, 10, 5, False),
            (AlertOperator.EQ, 5, 5, True),
            (AlertOperator.EQ, 5, 6, False),
            (AlertOperator.GTE, 5, 5, True),
            (AlertOperator.GTE, 4, 5, False),
            (AlertOperator.LTE, 5, 5, True),
            (AlertOperator.LTE, 6, 5, False),
        ],
    )
    def test_operators(
        self, operator: AlertOperator, current: int, threshold: int, expected: bool
    ) -> None:
        assert compare(operator, current, threshold) is expected

    def test_decimal_precision(self) -> None:
        # Floats would silently misbehave here (0.1 + 0.2 != 0.3); Decimal via str() must not.
        assert compare(AlertOperator.EQ, Decimal("90.10"), "90.10") is True


class TestPercentIncrease:
    def test_normal_increase(self) -> None:
        assert percent_increase(100, 150) == Decimal(50)

    def test_decrease_is_negative(self) -> None:
        assert percent_increase(100, 50) == Decimal(-50)

    def test_zero_previous_returns_zero_not_infinity(self) -> None:
        assert percent_increase(0, 100) == Decimal(0)


class TestRollingAverage:
    def test_normal(self) -> None:
        assert rolling_average([10, 20, 30]) == Decimal(20)

    def test_empty_returns_zero(self) -> None:
        assert rolling_average([]) == Decimal(0)


class TestEvaluateComposite:
    def test_leaf(self) -> None:
        cond = LeafCondition(field="cost", operator=AlertOperator.GT, threshold=100)
        assert evaluate(cond, {"cost": 150}) is True
        assert evaluate(cond, {"cost": 50}) is False

    def test_and_all_true(self) -> None:
        cond = CompositeCondition(
            logic=LogicalOperator.AND,
            children=[
                LeafCondition(field="cost", operator=AlertOperator.GT, threshold=100),
                LeafCondition(field="requests", operator=AlertOperator.GT, threshold=10),
            ],
        )
        assert evaluate(cond, {"cost": 150, "requests": 20}) is True
        assert evaluate(cond, {"cost": 150, "requests": 5}) is False

    def test_or_any_true(self) -> None:
        cond = CompositeCondition(
            logic=LogicalOperator.OR,
            children=[
                LeafCondition(field="cost", operator=AlertOperator.GT, threshold=1000),
                LeafCondition(field="requests", operator=AlertOperator.GT, threshold=10),
            ],
        )
        assert evaluate(cond, {"cost": 1, "requests": 20}) is True
        assert evaluate(cond, {"cost": 1, "requests": 1}) is False

    def test_not(self) -> None:
        cond = CompositeCondition(
            logic=LogicalOperator.NOT,
            children=[LeafCondition(field="cost", operator=AlertOperator.GT, threshold=100)],
        )
        assert evaluate(cond, {"cost": 50}) is True
        assert evaluate(cond, {"cost": 150}) is False

    def test_not_requires_exactly_one_child(self) -> None:
        cond = CompositeCondition(
            logic=LogicalOperator.NOT,
            children=[
                LeafCondition(field="a", operator=AlertOperator.GT, threshold=1),
                LeafCondition(field="b", operator=AlertOperator.GT, threshold=1),
            ],
        )
        with pytest.raises(ValueError, match="NOT requires exactly one"):
            evaluate(cond, {"a": 2, "b": 2})

    def test_missing_field_raises_keyerror(self) -> None:
        cond = LeafCondition(field="missing", operator=AlertOperator.GT, threshold=1)
        with pytest.raises(KeyError):
            evaluate(cond, {})

    def test_nested_composite(self) -> None:
        # (cost > 100 AND requests > 10) OR NOT(healthy)
        cond = CompositeCondition(
            logic=LogicalOperator.OR,
            children=[
                CompositeCondition(
                    logic=LogicalOperator.AND,
                    children=[
                        LeafCondition(field="cost", operator=AlertOperator.GT, threshold=100),
                        LeafCondition(field="requests", operator=AlertOperator.GT, threshold=10),
                    ],
                ),
                CompositeCondition(
                    logic=LogicalOperator.NOT,
                    children=[
                        LeafCondition(field="healthy", operator=AlertOperator.EQ, threshold=1)
                    ],
                ),
            ],
        )
        assert evaluate(cond, {"cost": 1, "requests": 1, "healthy": 0}) is True
        assert evaluate(cond, {"cost": 1, "requests": 1, "healthy": 1}) is False


# ── dedup.py ─────────────────────────────────────────────────────────────────


class TestDedup:
    def test_build_dedup_key_deterministic(self) -> None:
        k1 = build_dedup_key(AlertType.PROVIDER_ERROR, "provider:openai")
        k2 = build_dedup_key(AlertType.PROVIDER_ERROR, "provider:openai")
        assert k1 == k2

    def test_build_dedup_key_differs_by_type(self) -> None:
        k1 = build_dedup_key(AlertType.PROVIDER_ERROR, "provider:openai")
        k2 = build_dedup_key(AlertType.PROVIDER_RECOVERY, "provider:openai")
        assert k1 != k2

    def test_build_dedup_key_differs_by_scope(self) -> None:
        k1 = build_dedup_key(AlertType.PROVIDER_ERROR, "provider:openai")
        k2 = build_dedup_key(AlertType.PROVIDER_ERROR, "provider:anthropic")
        assert k1 != k2

    def test_key_within_column_limit(self) -> None:
        assert len(build_dedup_key(AlertType.PROVIDER_ERROR, "x" * 5000)) <= 255

    def test_scope_helpers(self) -> None:
        pid = uuid.uuid4()
        assert budget_scope(pid) == f"project:{pid}"
        kid = uuid.uuid4()
        assert api_key_scope(kid) == f"api_key:{kid}"
        assert membership_scope(_ORG_ID, "a@b.com") == f"membership:{_ORG_ID}:a@b.com"


# ── suppression.py ───────────────────────────────────────────────────────────


def _make_suppression(scope: SuppressionScope, target: str | None) -> AlertSuppression:
    s = MagicMock(spec=AlertSuppression)
    s.scope = scope
    s.target = target
    return s


class TestSuppression:
    @pytest.mark.asyncio
    async def test_no_suppressions_active(self) -> None:
        session = AsyncMock()
        with patch(
            "app.alerts.suppression.AlertSuppressionRepository"
        ) as repo_cls:
            repo_cls.return_value.list_active = AsyncMock(return_value=[])
            result = await is_suppressed(
                session, organization_id=_ORG_ID, alert_type=AlertType.PROVIDER_ERROR, provider=None
            )
        assert result is None

    @pytest.mark.asyncio
    async def test_organization_scope_always_suppresses(self) -> None:
        session = AsyncMock()
        org_suppression = _make_suppression(SuppressionScope.ORGANIZATION, None)
        with patch("app.alerts.suppression.AlertSuppressionRepository") as repo_cls:
            repo_cls.return_value.list_active = AsyncMock(return_value=[org_suppression])
            result = await is_suppressed(
                session,
                organization_id=_ORG_ID,
                alert_type=AlertType.BUDGET_EXCEEDED,
                provider=None,
            )
        assert result is org_suppression

    @pytest.mark.asyncio
    async def test_alert_type_scope_matches_only_that_type(self) -> None:
        session = AsyncMock()
        type_suppression = _make_suppression(
            SuppressionScope.ALERT_TYPE, AlertType.PROVIDER_ERROR.value
        )
        with patch("app.alerts.suppression.AlertSuppressionRepository") as repo_cls:
            repo_cls.return_value.list_active = AsyncMock(return_value=[type_suppression])
            matched = await is_suppressed(
                session, organization_id=_ORG_ID, alert_type=AlertType.PROVIDER_ERROR, provider=None
            )
            unmatched = await is_suppressed(
                session,
                organization_id=_ORG_ID,
                alert_type=AlertType.BUDGET_EXCEEDED,
                provider=None,
            )
        assert matched is type_suppression
        assert unmatched is None

    @pytest.mark.asyncio
    async def test_provider_scope_requires_provider_match(self) -> None:
        session = AsyncMock()
        provider_suppression = _make_suppression(SuppressionScope.PROVIDER, "openai")
        with patch("app.alerts.suppression.AlertSuppressionRepository") as repo_cls:
            repo_cls.return_value.list_active = AsyncMock(return_value=[provider_suppression])
            matched = await is_suppressed(
                session,
                organization_id=_ORG_ID,
                alert_type=AlertType.PROVIDER_ERROR,
                provider="openai",
            )
            no_provider = await is_suppressed(
                session, organization_id=_ORG_ID, alert_type=AlertType.PROVIDER_ERROR, provider=None
            )
            wrong_provider = await is_suppressed(
                session,
                organization_id=_ORG_ID,
                alert_type=AlertType.PROVIDER_ERROR,
                provider="anthropic",
            )
        assert matched is provider_suppression
        assert no_provider is None
        assert wrong_provider is None


# ── preferences.py ───────────────────────────────────────────────────────────


class TestPreferences:
    @pytest.mark.asyncio
    async def test_get_or_default_returns_stored_row(self) -> None:
        session = AsyncMock()
        stored = MagicMock(spec=AlertPreference)
        with patch("app.alerts.preferences.AlertPreferenceRepository") as repo_cls:
            repo_cls.return_value.get_for_user = AsyncMock(return_value=stored)
            result = await get_or_default(session, organization_id=_ORG_ID, user_id=_USER_ID)
        assert result is stored

    @pytest.mark.asyncio
    async def test_get_or_default_falls_back_to_unsaved_default(self) -> None:
        session = AsyncMock()
        with patch("app.alerts.preferences.AlertPreferenceRepository") as repo_cls:
            repo_cls.return_value.get_for_user = AsyncMock(return_value=None)
            result = await get_or_default(session, organization_id=_ORG_ID, user_id=_USER_ID)
        assert result.enabled_alert_types == []
        assert result.min_severity == AlertSeverity.INFO
        assert result.immediate_notifications is True

    def test_minute_of_day(self) -> None:
        assert minute_of_day(time(hour=0, minute=0)) == 0
        assert minute_of_day(time(hour=1, minute=30)) == 90
        assert minute_of_day(time(hour=23, minute=59)) == 1439

    def test_quiet_hours_none_configured(self) -> None:
        pref = MagicMock(spec=AlertPreference)
        pref.quiet_hours_start_minute = None
        pref.quiet_hours_end_minute = None
        assert is_within_quiet_hours(pref, now=_NOW) is False

    def test_quiet_hours_normal_window(self) -> None:
        pref = MagicMock(spec=AlertPreference)
        pref.quiet_hours_start_minute = 22 * 60  # 22:00
        pref.quiet_hours_end_minute = 7 * 60  # 07:00 (wraps midnight)
        inside_late = _NOW.replace(hour=23, minute=0)
        inside_early = _NOW.replace(hour=3, minute=0)
        outside = _NOW.replace(hour=12, minute=0)
        assert is_within_quiet_hours(pref, now=inside_late) is True
        assert is_within_quiet_hours(pref, now=inside_early) is True
        assert is_within_quiet_hours(pref, now=outside) is False

    def test_quiet_hours_non_wrapping_window(self) -> None:
        pref = MagicMock(spec=AlertPreference)
        pref.quiet_hours_start_minute = 9 * 60
        pref.quiet_hours_end_minute = 17 * 60
        inside = _NOW.replace(hour=12, minute=0)
        outside = _NOW.replace(hour=20, minute=0)
        assert is_within_quiet_hours(pref, now=inside) is True
        assert is_within_quiet_hours(pref, now=outside) is False

    def test_should_surface_severity_threshold(self) -> None:
        pref = MagicMock(spec=AlertPreference)
        pref.min_severity = AlertSeverity.HIGH
        pref.enabled_alert_types = []
        low = MagicMock(spec=Alert)
        low.severity = AlertSeverity.LOW
        low.alert_type = AlertType.PROVIDER_ERROR
        critical = MagicMock(spec=Alert)
        critical.severity = AlertSeverity.CRITICAL
        critical.alert_type = AlertType.PROVIDER_ERROR
        assert should_surface(pref, low) is False
        assert should_surface(pref, critical) is True

    def test_should_surface_type_allowlist(self) -> None:
        pref = MagicMock(spec=AlertPreference)
        pref.min_severity = AlertSeverity.INFO
        pref.enabled_alert_types = [AlertType.BUDGET_EXCEEDED.value]
        matching = MagicMock(spec=Alert)
        matching.severity = AlertSeverity.INFO
        matching.alert_type = AlertType.BUDGET_EXCEEDED
        other = MagicMock(spec=Alert)
        other.severity = AlertSeverity.INFO
        other.alert_type = AlertType.PROVIDER_ERROR
        assert should_surface(pref, matching) is True
        assert should_surface(pref, other) is False


# ── rule_engine.py ───────────────────────────────────────────────────────────


class TestRuleEngine:
    @pytest.mark.asyncio
    async def test_matches_rules_over_threshold(self) -> None:
        session = AsyncMock()
        rule = MagicMock(spec=AlertRule)
        rule.operator = AlertOperator.GT
        rule.threshold = Decimal(90)
        with patch("app.alerts.rule_engine.AlertRuleRepository") as repo_cls:
            repo_cls.return_value.list_enabled_for_type = AsyncMock(return_value=[rule])
            engine = RuleEngine(session)
            matched = await engine.evaluate_type(
                organization_id=_ORG_ID, alert_type=AlertType.BUDGET_THRESHOLD, current_value=95.0
            )
        assert matched == [rule]

    @pytest.mark.asyncio
    async def test_no_match_below_threshold(self) -> None:
        session = AsyncMock()
        rule = MagicMock(spec=AlertRule)
        rule.operator = AlertOperator.GT
        rule.threshold = Decimal(90)
        with patch("app.alerts.rule_engine.AlertRuleRepository") as repo_cls:
            repo_cls.return_value.list_enabled_for_type = AsyncMock(return_value=[rule])
            engine = RuleEngine(session)
            matched = await engine.evaluate_type(
                organization_id=_ORG_ID, alert_type=AlertType.BUDGET_THRESHOLD, current_value=50.0
            )
        assert matched == []

    @pytest.mark.asyncio
    async def test_no_rules_configured_returns_empty(self) -> None:
        session = AsyncMock()
        with patch("app.alerts.rule_engine.AlertRuleRepository") as repo_cls:
            repo_cls.return_value.list_enabled_for_type = AsyncMock(return_value=[])
            engine = RuleEngine(session)
            matched = await engine.evaluate_type(
                organization_id=_ORG_ID, alert_type=AlertType.BUDGET_THRESHOLD, current_value=999.0
            )
        assert matched == []


# ── dispatcher.py (AlertService) ────────────────────────────────────────────


def _fire_kwargs(**overrides: Any) -> dict[str, Any]:
    base = {
        "organization_id": _ORG_ID,
        "alert_type": AlertType.PROVIDER_ERROR,
        "severity": AlertSeverity.HIGH,
        "title": "Provider failing",
        "message": "openai is failing",
        "source": "ingestion",
        "scope": "provider:openai",
    }
    base.update(overrides)
    return base


class TestAlertServiceFire:
    @pytest.mark.asyncio
    async def test_suppressed_alert_returns_none_and_does_not_persist(self) -> None:
        session = AsyncMock()
        event_bus = AsyncMock()
        suppression = MagicMock(spec=AlertSuppression)
        with (
            patch("app.alerts.dispatcher.is_suppressed", new=AsyncMock(return_value=suppression)),
            patch("app.alerts.dispatcher.AlertRepository") as repo_cls,
        ):
            service = AlertService(session, event_bus)
            result = await service.fire(**_fire_kwargs())
        assert result is None
        repo_cls.return_value.create.assert_not_called()
        event_bus.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_new_alert_created_and_published(self) -> None:
        session = AsyncMock()
        event_bus = AsyncMock()
        created = MagicMock(spec=Alert)
        created.id = uuid.uuid4()
        created.organization_id = _ORG_ID
        created.alert_type = AlertType.PROVIDER_ERROR
        created.severity = AlertSeverity.HIGH
        created.status = AlertStatus.OPEN
        created.title = "Provider failing"
        created.message = "openai is failing"
        created.occurrence_count = 1
        created.alert_metadata = {}

        with (
            patch("app.alerts.dispatcher.is_suppressed", new=AsyncMock(return_value=None)),
            patch("app.alerts.dispatcher.AlertRepository") as repo_cls,
        ):
            repo_cls.return_value.find_open_by_dedup_key = AsyncMock(return_value=None)
            repo_cls.return_value.create = AsyncMock(return_value=created)
            service = AlertService(session, event_bus)
            result = await service.fire(**_fire_kwargs())

        assert result is created
        repo_cls.return_value.create.assert_awaited_once()
        event_bus.publish.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_duplicate_occurrence_increments_existing(self) -> None:
        session = AsyncMock()
        event_bus = AsyncMock()
        existing = MagicMock(spec=Alert)
        existing.id = uuid.uuid4()
        existing.organization_id = _ORG_ID
        existing.alert_type = AlertType.PROVIDER_ERROR
        existing.severity = AlertSeverity.HIGH
        existing.status = AlertStatus.OPEN
        existing.title = "old title"
        existing.message = "old message"
        existing.occurrence_count = 5
        existing.alert_metadata = {"foo": "bar"}

        with (
            patch("app.alerts.dispatcher.is_suppressed", new=AsyncMock(return_value=None)),
            patch("app.alerts.dispatcher.AlertRepository") as repo_cls,
        ):
            repo_cls.return_value.find_open_by_dedup_key = AsyncMock(return_value=existing)
            service = AlertService(session, event_bus)
            result = await service.fire(**_fire_kwargs(message="new occurrence"))

        assert result is existing
        assert existing.occurrence_count == 6
        assert existing.message == "new occurrence"
        repo_cls.return_value.create.assert_not_called()
        event_bus.publish.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_event_bus_failure_does_not_raise(self) -> None:
        """EventBus.publish() never raises per its own contract, but the
        dispatcher must also not introduce a new failure mode around it."""
        session = AsyncMock()
        event_bus = AsyncMock()
        event_bus.publish = AsyncMock(return_value=None)  # simulates the never-raise contract
        created = MagicMock(spec=Alert)
        created.id = uuid.uuid4()
        created.organization_id = _ORG_ID
        created.alert_type = AlertType.PROVIDER_ERROR
        created.severity = AlertSeverity.HIGH
        created.status = AlertStatus.OPEN
        created.title = "t"
        created.message = "m"
        created.occurrence_count = 1
        created.alert_metadata = {}

        with (
            patch("app.alerts.dispatcher.is_suppressed", new=AsyncMock(return_value=None)),
            patch("app.alerts.dispatcher.AlertRepository") as repo_cls,
        ):
            repo_cls.return_value.find_open_by_dedup_key = AsyncMock(return_value=None)
            repo_cls.return_value.create = AsyncMock(return_value=created)
            service = AlertService(session, event_bus)
            result = await service.fire(**_fire_kwargs())
        assert result is created


# ── API: alert lifecycle + org isolation ────────────────────────────────────


async def _mock_org_membership_owner() -> object:
    """RequireQueryPermission needs a real MembershipRole for has_permission()
    to succeed — unlike the plain membership-existence checks elsewhere in
    this suite, a bare MagicMock(spec=Membership) would fail every
    permission check since its `.role` attribute isn't a real enum member."""
    from app.models.membership import Membership, MembershipRole

    m = MagicMock(spec=Membership)
    m.role = MembershipRole.OWNER
    return m


def _mock_alert(
    *, organization_id: uuid.UUID, alert_status: AlertStatus = AlertStatus.OPEN
) -> Alert:
    a = MagicMock(spec=Alert)
    a.id = uuid.uuid4()
    a.organization_id = organization_id
    a.alert_type = AlertType.BUDGET_EXCEEDED
    a.severity = AlertSeverity.CRITICAL
    a.status = alert_status
    a.title = "Budget exceeded"
    a.message = "over budget"
    a.source = "ingestion"
    a.occurrence_count = 1
    a.alert_metadata = {}
    a.first_occurred_at = _NOW
    a.last_occurred_at = _NOW
    a.acknowledged_by = None
    a.acknowledged_at = None
    a.acknowledgement_reason = None
    a.resolved_at = None
    a.dismissed_at = None
    a.created_at = _NOW
    return a


class TestAlertsApiLifecycle:
    @pytest.mark.asyncio
    async def test_acknowledge_open_alert_succeeds(self, app: Any) -> None:
        from httpx import ASGITransport, AsyncClient

        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User

        mock_user = MagicMock(spec=User)
        mock_user.id = _USER_ID

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        alert = _mock_alert(organization_id=_ORG_ID)
        session = AsyncMock()

        async def mock_get_db():
            yield session

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership_owner
        app.dependency_overrides[get_db] = mock_get_db
        try:
            with (
                patch("app.api.v1.alerts.AlertRepository") as repo_cls,
            ):
                repo_cls.return_value.get = AsyncMock(return_value=alert)

                async def _update(instance: Alert, **kwargs: Any) -> Alert:
                    for k, v in kwargs.items():
                        setattr(instance, k, v)
                    return instance

                repo_cls.return_value.update = AsyncMock(side_effect=_update)

                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(
                        f"/v1/alerts/{alert.id}/acknowledge",
                        params={"organization_id": str(_ORG_ID)},
                        json={"reason": "investigating"},
                    )
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "acknowledged"
            assert body["acknowledgement_reason"] == "investigating"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_acknowledge_already_acknowledged_is_409(self, app: Any) -> None:
        from httpx import ASGITransport, AsyncClient

        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User

        mock_user = MagicMock(spec=User)
        mock_user.id = _USER_ID

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        alert = _mock_alert(organization_id=_ORG_ID, alert_status=AlertStatus.ACKNOWLEDGED)
        session = AsyncMock()

        async def mock_get_db():
            yield session

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership_owner
        app.dependency_overrides[get_db] = mock_get_db
        try:
            with patch("app.api.v1.alerts.AlertRepository") as repo_cls:
                repo_cls.return_value.get = AsyncMock(return_value=alert)
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(
                        f"/v1/alerts/{alert.id}/acknowledge",
                        params={"organization_id": str(_ORG_ID)},
                        json={},
                    )
            assert resp.status_code == 409
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_cross_org_alert_is_404_not_leaked(self, app: Any) -> None:
        """An alert belonging to a different organization must never be
        acknowledgeable (or even visible) via another org's membership,
        even if the caller knows its ID — the core "no cross-organization
        notification leakage" success criterion from the ticket."""
        from httpx import ASGITransport, AsyncClient

        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User

        mock_user = MagicMock(spec=User)
        mock_user.id = _USER_ID

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        # Alert belongs to _OTHER_ORG_ID, caller is authenticated against _ORG_ID.
        alert = _mock_alert(organization_id=_OTHER_ORG_ID)
        session = AsyncMock()

        async def mock_get_db():
            yield session

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership_owner
        app.dependency_overrides[get_db] = mock_get_db
        try:
            with patch("app.api.v1.alerts.AlertRepository") as repo_cls:
                repo_cls.return_value.get = AsyncMock(return_value=alert)
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(
                        f"/v1/alerts/{alert.id}/acknowledge",
                        params={"organization_id": str(_ORG_ID)},
                        json={},
                    )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_reopen_open_alert_is_409(self, app: Any) -> None:
        from httpx import ASGITransport, AsyncClient

        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User

        mock_user = MagicMock(spec=User)
        mock_user.id = _USER_ID

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        alert = _mock_alert(organization_id=_ORG_ID, alert_status=AlertStatus.OPEN)
        session = AsyncMock()

        async def mock_get_db():
            yield session

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership_owner
        app.dependency_overrides[get_db] = mock_get_db
        try:
            with patch("app.api.v1.alerts.AlertRepository") as repo_cls:
                repo_cls.return_value.get = AsyncMock(return_value=alert)
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(
                        f"/v1/alerts/{alert.id}/reopen",
                        params={"organization_id": str(_ORG_ID)},
                    )
            assert resp.status_code == 409
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_resolve_then_reopen_round_trip(self, app: Any) -> None:
        from httpx import ASGITransport, AsyncClient

        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User

        mock_user = MagicMock(spec=User)
        mock_user.id = _USER_ID

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        alert = _mock_alert(organization_id=_ORG_ID, alert_status=AlertStatus.OPEN)
        session = AsyncMock()

        async def mock_get_db():
            yield session

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership_owner
        app.dependency_overrides[get_db] = mock_get_db
        try:
            with patch("app.api.v1.alerts.AlertRepository") as repo_cls:
                repo_cls.return_value.get = AsyncMock(return_value=alert)

                async def _update(instance: Alert, **kwargs: Any) -> Alert:
                    for k, v in kwargs.items():
                        setattr(instance, k, v)
                    return instance

                repo_cls.return_value.update = AsyncMock(side_effect=_update)

                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resolve_resp = await ac.post(
                        f"/v1/alerts/{alert.id}/resolve",
                        params={"organization_id": str(_ORG_ID)},
                    )
                    assert resolve_resp.status_code == 200
                    assert resolve_resp.json()["status"] == "resolved"

                    reopen_resp = await ac.post(
                        f"/v1/alerts/{alert.id}/reopen",
                        params={"organization_id": str(_ORG_ID)},
                    )
                    assert reopen_resp.status_code == 200
                    assert reopen_resp.json()["status"] == "open"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_list_alerts_returns_filtered_results(self, app: Any) -> None:
        from httpx import ASGITransport, AsyncClient

        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User

        mock_user = MagicMock(spec=User)

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        alerts = [_mock_alert(organization_id=_ORG_ID) for _ in range(3)]
        session = AsyncMock()

        async def mock_get_db():
            yield session

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership_owner
        app.dependency_overrides[get_db] = mock_get_db
        try:
            with patch("app.api.v1.alerts.AlertRepository") as repo_cls:
                repo_cls.return_value.list_for_org = AsyncMock(return_value=alerts)
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.get(
                        "/v1/alerts",
                        params={
                            "organization_id": str(_ORG_ID),
                            "status": "open",
                            "severity": "critical",
                        },
                    )
            assert resp.status_code == 200
            body = resp.json()
            assert body["total"] == 3
            assert len(body["alerts"]) == 3
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_list_alerts_invalid_status_is_422(self, app: Any) -> None:
        from httpx import ASGITransport, AsyncClient

        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User

        mock_user = MagicMock(spec=User)

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        session = AsyncMock()

        async def mock_get_db():
            yield session

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership_owner
        app.dependency_overrides[get_db] = mock_get_db
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.get(
                    "/v1/alerts",
                    params={"organization_id": str(_ORG_ID), "status": "not-a-real-status"},
                )
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_requires_authentication(self, app: Any) -> None:
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/v1/alerts", params={"organization_id": str(_ORG_ID)})
        assert resp.status_code == 401


class TestAlertPreferencesApi:
    @pytest.mark.asyncio
    async def test_get_preferences_returns_defaults_when_unset(self, app: Any) -> None:
        from httpx import ASGITransport, AsyncClient

        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User

        mock_user = MagicMock(spec=User)
        mock_user.id = _USER_ID

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        session = AsyncMock()

        async def mock_get_db():
            yield session

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership_owner
        app.dependency_overrides[get_db] = mock_get_db
        try:
            with patch("app.alerts.preferences.AlertPreferenceRepository") as repo_cls:
                repo_cls.return_value.get_for_user = AsyncMock(return_value=None)
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.get(
                        "/v1/alerts/preferences", params={"organization_id": str(_ORG_ID)}
                    )
            assert resp.status_code == 200
            body = resp.json()
            assert body["min_severity"] == "info"
            assert body["enabled_alert_types"] == []
            assert body["quiet_hours_start"] is None
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_update_preferences_creates_row_lazily(self, app: Any) -> None:
        from httpx import ASGITransport, AsyncClient

        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User

        mock_user = MagicMock(spec=User)
        mock_user.id = _USER_ID

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        session = AsyncMock()

        async def mock_get_db():
            yield session

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership_owner
        app.dependency_overrides[get_db] = mock_get_db
        try:
            with (
                patch("app.api.v1.alerts.AlertPreferenceRepository") as repo_cls,
                patch("app.alerts.preferences.AlertPreferenceRepository") as pref_repo_cls,
            ):
                repo_cls.return_value.get_for_user = AsyncMock(return_value=None)
                pref_repo_cls.return_value.get_for_user = AsyncMock(return_value=None)

                async def _create(instance: AlertPreference) -> AlertPreference:
                    return instance

                repo_cls.return_value.create = AsyncMock(side_effect=_create)

                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.patch(
                        "/v1/alerts/preferences",
                        params={"organization_id": str(_ORG_ID)},
                        json={
                            "min_severity": "high",
                            "quiet_hours_start": "22:00",
                            "quiet_hours_end": "07:00",
                        },
                    )
            assert resp.status_code == 200
            body = resp.json()
            assert body["min_severity"] == "high"
            assert body["quiet_hours_start"] == "22:00"
            assert body["quiet_hours_end"] == "07:00"
        finally:
            app.dependency_overrides.clear()


class TestAlertRulesAndSuppressionsApi:
    @pytest.mark.asyncio
    async def test_create_rule(self, app: Any) -> None:
        from httpx import ASGITransport, AsyncClient

        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User

        mock_user = MagicMock(spec=User)
        mock_user.id = _USER_ID

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        session = AsyncMock()

        async def mock_get_db():
            yield session

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership_owner
        app.dependency_overrides[get_db] = mock_get_db
        try:
            with patch("app.api.v1.alerts.AlertRuleRepository") as repo_cls:

                async def _create(instance: AlertRule) -> AlertRule:
                    instance.created_at = _NOW
                    return instance

                repo_cls.return_value.create = AsyncMock(side_effect=_create)

                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(
                        "/v1/alerts/rules",
                        params={"organization_id": str(_ORG_ID)},
                        json={
                            "alert_type": "budget_threshold",
                            "name": "90% budget warning",
                            "severity": "high",
                            "operator": "gt",
                            "threshold": "90",
                        },
                    )
            assert resp.status_code == 201
            body = resp.json()
            assert body["alert_type"] == "budget_threshold"
            assert body["threshold"] == "90"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_create_rule_invalid_threshold_is_422(self, app: Any) -> None:
        from httpx import ASGITransport, AsyncClient

        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User

        mock_user = MagicMock(spec=User)
        mock_user.id = _USER_ID

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        session = AsyncMock()

        async def mock_get_db():
            yield session

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership_owner
        app.dependency_overrides[get_db] = mock_get_db
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.post(
                    "/v1/alerts/rules",
                    params={"organization_id": str(_ORG_ID)},
                    json={
                        "alert_type": "budget_threshold",
                        "name": "bad rule",
                        "operator": "gt",
                        "threshold": "not-a-number",
                    },
                )
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_delete_rule_cross_org_is_404(self, app: Any) -> None:
        from httpx import ASGITransport, AsyncClient

        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User

        mock_user = MagicMock(spec=User)

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        rule = MagicMock(spec=AlertRule)
        rule.id = uuid.uuid4()
        rule.organization_id = _OTHER_ORG_ID
        session = AsyncMock()

        async def mock_get_db():
            yield session

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership_owner
        app.dependency_overrides[get_db] = mock_get_db
        try:
            with patch("app.api.v1.alerts.AlertRuleRepository") as repo_cls:
                repo_cls.return_value.get = AsyncMock(return_value=rule)
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.delete(
                        f"/v1/alerts/rules/{rule.id}", params={"organization_id": str(_ORG_ID)}
                    )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_create_suppression_organization_scope(self, app: Any) -> None:
        from httpx import ASGITransport, AsyncClient

        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user, get_query_org_membership
        from app.models.user import User

        mock_user = MagicMock(spec=User)
        mock_user.id = _USER_ID

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        session = AsyncMock()

        async def mock_get_db():
            yield session

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_query_org_membership] = _mock_org_membership_owner
        app.dependency_overrides[get_db] = mock_get_db
        try:
            with patch("app.api.v1.alerts.AlertSuppressionRepository") as repo_cls:

                async def _create(instance: AlertSuppression) -> AlertSuppression:
                    instance.created_at = _NOW
                    return instance

                repo_cls.return_value.create = AsyncMock(side_effect=_create)

                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(
                        "/v1/alerts/suppressions",
                        params={"organization_id": str(_ORG_ID)},
                        json={"scope": "organization", "reason": "maintenance window"},
                    )
            assert resp.status_code == 201
            body = resp.json()
            assert body["scope"] == "organization"
            assert body["ends_at"] is None
        finally:
            app.dependency_overrides.clear()
