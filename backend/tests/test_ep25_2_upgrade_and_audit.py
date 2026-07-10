"""Tests for EP-25.2 — Personal -> Business upgrade + ownership audit.

Covers:
  - AuthService.upgrade_to_business(): reuses the existing personal
    Organization row (same id/slug), flips is_personal, applies the
    optional name (or the "My Team" default), raises
    NoPersonalWorkspaceError when the caller has none.
  - POST /v1/auth/upgrade-to-business (API layer).
  - The alert-rule ownership-consistency fix: PATCH /v1/alerts/rules/{id}
    now exists (create+delete previously had no edit).
  - A light regression pin of the EP-24 permission-consistency invariant
    (PROJECT_DELETE still granted to MEMBER) so this EP's audit doesn't
    silently regress it.

All tests are hermetic — no network calls, no real database.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.exceptions import NoPersonalWorkspaceError
from app.auth.rbac import ROLE_PERMISSIONS, Permission
from app.auth.service import AuthService
from app.config.settings import Settings
from app.models.alert import AlertOperator, AlertRule, AlertSeverity, AlertType
from app.models.membership import Membership, MembershipRole
from app.models.user import User
from tests.conftest import make_org, make_user

_ORG_ID = uuid.uuid4()


def _test_settings(**overrides: Any) -> Settings:
    kwargs: dict[str, Any] = {
        "app_env": "testing",
        "app_secret_key": "test-secret-key-with-at-least-32-chars!!",
        "jwt_secret": "test-jwt-secret-for-unit-tests-only!!",
    }
    kwargs.update(overrides)
    return Settings(**kwargs)


# ── AuthService.upgrade_to_business ─────────────────────────────────────────


class TestUpgradeToBusinessService:
    def _service(self) -> AuthService:
        svc = AuthService(AsyncMock(), _test_settings())
        svc._membership_repo = AsyncMock()
        svc._org_repo = AsyncMock()
        svc._email = AsyncMock()
        svc._email.send_welcome_email = AsyncMock()
        return svc

    def _membership_for(self, org: Any, *, role: MembershipRole) -> Any:
        m = MagicMock(spec=Membership)
        m.organization = org
        m.role = role
        return m

    @pytest.mark.asyncio
    async def test_flips_is_personal_and_reuses_the_same_org_row(self) -> None:
        svc = self._service()
        user = make_user(email="solo@example.com")
        personal_org = make_org(is_personal=True, name="Solo's Workspace", slug="solo-workspace")
        svc._membership_repo.list_by_user_email_with_orgs = AsyncMock(
            return_value=[self._membership_for(personal_org, role=MembershipRole.OWNER)]
        )

        async def _update(org: Any, **kwargs: Any) -> Any:
            for k, v in kwargs.items():
                setattr(org, k, v)
            return org

        svc._org_repo.update = AsyncMock(side_effect=_update)

        result = await svc.upgrade_to_business(user=user, organization_name="Acme Inc")

        assert result is personal_org
        assert result.id == personal_org.id
        assert result.slug == "solo-workspace"
        assert result.is_personal is False
        assert result.name == "Acme Inc"
        svc._email.send_welcome_email.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_defaults_to_my_team_when_no_name_supplied(self) -> None:
        async def _update(org: Any, **kwargs: Any) -> Any:
            for k, v in kwargs.items():
                setattr(org, k, v)
            return org

        svc = self._service()
        user = make_user(email="solo2@example.com")
        personal_org = make_org(is_personal=True)
        svc._membership_repo.list_by_user_email_with_orgs = AsyncMock(
            return_value=[self._membership_for(personal_org, role=MembershipRole.OWNER)]
        )
        svc._org_repo.update = AsyncMock(side_effect=_update)
        result = await svc.upgrade_to_business(user=user, organization_name=None)
        assert result.name == "My Team"

        svc2 = self._service()
        personal_org2 = make_org(is_personal=True)
        svc2._membership_repo.list_by_user_email_with_orgs = AsyncMock(
            return_value=[self._membership_for(personal_org2, role=MembershipRole.OWNER)]
        )
        svc2._org_repo.update = AsyncMock(side_effect=_update)
        result2 = await svc2.upgrade_to_business(user=user, organization_name="   ")
        assert result2.name == "My Team"

    @pytest.mark.asyncio
    async def test_raises_when_no_personal_workspace_exists(self) -> None:
        svc = self._service()
        user = make_user(email="nobody@example.com")
        business_org = make_org(is_personal=False)
        svc._membership_repo.list_by_user_email_with_orgs = AsyncMock(
            return_value=[self._membership_for(business_org, role=MembershipRole.OWNER)]
        )

        with pytest.raises(NoPersonalWorkspaceError):
            await svc.upgrade_to_business(user=user)

    @pytest.mark.asyncio
    async def test_only_considers_org_where_caller_is_owner(self) -> None:
        svc = self._service()
        user = make_user(email="viewer@example.com")
        personal_org = make_org(is_personal=True)
        svc._membership_repo.list_by_user_email_with_orgs = AsyncMock(
            return_value=[self._membership_for(personal_org, role=MembershipRole.VIEWER)]
        )

        with pytest.raises(NoPersonalWorkspaceError):
            await svc.upgrade_to_business(user=user)


# ── POST /v1/auth/upgrade-to-business ───────────────────────────────────────


def _override_current_user(app: Any) -> User:
    from app.api.deps import get_db
    from app.auth.dependencies import get_current_user

    mock_user = MagicMock(spec=User)
    mock_user.id = uuid.uuid4()
    mock_user.email = "solo@example.com"
    mock_user.display_name = "Solo Dev"

    async def mock_get_user() -> User:
        return mock_user  # type: ignore[return-value]

    async def mock_get_db() -> Any:
        yield AsyncMock()

    app.dependency_overrides[get_current_user] = mock_get_user
    app.dependency_overrides[get_db] = mock_get_db
    return mock_user  # type: ignore[return-value]


class TestUpgradeToBusinessEndpoint:
    @pytest.mark.asyncio
    async def test_upgrade_endpoint_success(self, app: Any) -> None:
        _override_current_user(app)
        personal_org = make_org(is_personal=True, name="Solo's Workspace", slug="solo-workspace")
        personal_org.is_personal = False
        personal_org.name = "Acme Inc"

        with patch(
            "app.api.v1.auth.AuthService.upgrade_to_business",
            new=AsyncMock(return_value=personal_org),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/v1/auth/upgrade-to-business",
                    json={"organization_name": "Acme Inc"},
                    headers={"Authorization": "Bearer test"},
                )
        app.dependency_overrides.clear()

        assert resp.status_code == 200
        body = resp.json()
        assert body["is_personal"] is False
        assert body["name"] == "Acme Inc"

    @pytest.mark.asyncio
    async def test_upgrade_endpoint_404_when_no_personal_workspace(self, app: Any) -> None:
        _override_current_user(app)

        with patch(
            "app.api.v1.auth.AuthService.upgrade_to_business",
            new=AsyncMock(side_effect=NoPersonalWorkspaceError),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/v1/auth/upgrade-to-business",
                    json={},
                    headers={"Authorization": "Bearer test"},
                )
        app.dependency_overrides.clear()

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_upgrade_endpoint_requires_authentication(self, app: Any) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/v1/auth/upgrade-to-business", json={})
        assert resp.status_code == 401


# ── Alert rule PATCH (ownership-consistency audit fix) ──────────────────────


def _override_query_membership(app: Any, *, role: MembershipRole) -> AsyncMock:
    from app.api.deps import get_db
    from app.auth.dependencies import get_query_org_membership

    membership = MagicMock(spec=Membership)
    membership.id = uuid.uuid4()
    membership.role = role
    membership.organization_id = _ORG_ID
    membership.user_id = uuid.uuid4()

    async def mock_membership() -> Membership:
        return membership  # type: ignore[return-value]

    mock_session = AsyncMock()

    async def mock_get_db() -> Any:
        yield mock_session

    app.dependency_overrides[get_query_org_membership] = mock_membership
    app.dependency_overrides[get_db] = mock_get_db
    return mock_session


def _make_rule(**overrides: Any) -> AlertRule:
    rule = MagicMock(spec=AlertRule)
    rule.id = uuid.uuid4()
    rule.organization_id = _ORG_ID
    rule.alert_type = AlertType.BUDGET_THRESHOLD
    rule.name = "Original name"
    rule.severity = AlertSeverity.MEDIUM
    rule.operator = AlertOperator.GT
    rule.threshold = Decimal("80")
    rule.enabled = True
    rule.created_at = datetime.now(UTC)
    for k, v in overrides.items():
        setattr(rule, k, v)
    return rule


class TestAlertRuleUpdateEndpoint:
    @pytest.mark.asyncio
    async def test_admin_can_update_a_rule(self, app: Any) -> None:
        _override_query_membership(app, role=MembershipRole.ADMIN)
        rule = _make_rule()

        async def _update(target: Any, **kwargs: Any) -> Any:
            for k, v in kwargs.items():
                setattr(target, k, v)
            return target

        mock_repo = MagicMock(
            get=AsyncMock(return_value=rule), update=AsyncMock(side_effect=_update)
        )
        with patch("app.api.v1.alerts.AlertRuleRepository", return_value=mock_repo):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.patch(
                    f"/v1/alerts/rules/{rule.id}",
                    params={"organization_id": str(_ORG_ID)},
                    json={"enabled": False, "name": "Renamed"},
                    headers={"Authorization": "Bearer test"},
                )
        app.dependency_overrides.clear()

        assert resp.status_code == 200
        body = resp.json()
        assert body["enabled"] is False
        assert body["name"] == "Renamed"

    @pytest.mark.asyncio
    async def test_viewer_cannot_update_a_rule(self, app: Any) -> None:
        _override_query_membership(app, role=MembershipRole.VIEWER)
        rule = _make_rule()

        with patch(
            "app.api.v1.alerts.AlertRuleRepository",
            return_value=MagicMock(get=AsyncMock(return_value=rule)),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.patch(
                    f"/v1/alerts/rules/{rule.id}",
                    params={"organization_id": str(_ORG_ID)},
                    json={"enabled": False},
                    headers={"Authorization": "Bearer test"},
                )
        app.dependency_overrides.clear()

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_update_unknown_rule_is_404(self, app: Any) -> None:
        _override_query_membership(app, role=MembershipRole.ADMIN)

        with patch(
            "app.api.v1.alerts.AlertRuleRepository",
            return_value=MagicMock(get=AsyncMock(return_value=None)),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.patch(
                    f"/v1/alerts/rules/{uuid.uuid4()}",
                    params={"organization_id": str(_ORG_ID)},
                    json={"enabled": False},
                    headers={"Authorization": "Bearer test"},
                )
        app.dependency_overrides.clear()

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_rejects_a_rule_from_another_org(self, app: Any) -> None:
        _override_query_membership(app, role=MembershipRole.ADMIN)
        other_org_rule = _make_rule(organization_id=uuid.uuid4())

        with patch(
            "app.api.v1.alerts.AlertRuleRepository",
            return_value=MagicMock(get=AsyncMock(return_value=other_org_rule)),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.patch(
                    f"/v1/alerts/rules/{other_org_rule.id}",
                    params={"organization_id": str(_ORG_ID)},
                    json={"enabled": False},
                    headers={"Authorization": "Bearer test"},
                )
        app.dependency_overrides.clear()

        assert resp.status_code == 404


# ── Regression pin: EP-24's permission-consistency invariant ────────────────


class TestPermissionConsistencyStillHolds:
    """Guards against a future PR silently reopening the EP-24 audit's fix."""

    def test_member_still_has_project_write_and_delete(self) -> None:
        member_perms = ROLE_PERMISSIONS[MembershipRole.MEMBER]
        assert Permission.PROJECT_WRITE in member_perms
        assert Permission.PROJECT_DELETE in member_perms

    def test_owner_has_every_permission(self) -> None:
        assert ROLE_PERMISSIONS[MembershipRole.OWNER] == frozenset(Permission)
