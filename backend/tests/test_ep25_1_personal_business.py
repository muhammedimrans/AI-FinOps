"""Tests for Personal vs Business account types (EP-25.1).

Covers:
  - AuthService.register(): personal creates one (hidden) workspace;
    business additionally creates a second, real (is_personal=False)
    workspace and returns it as "the" workspace.
  - InvitationService.create_invitation() refuses a personal organization.
  - API guards: POST /members, PATCH /{org_id}, POST /invitations all 400
    for a personal organization.
  - AuthService.delete_account()'s cascade soft-deletes every dependent
    resource (projects, provider connections, budgets, API keys, pending
    invitations) for each organization the account solely owns.
  - RBAC "bypass" for personal orgs is structural: the sole member of a
    personal org is always OWNER, and OWNER already holds every permission
    — no special-cased bypass branch exists or is needed.

All tests are hermetic — no network calls, no real database.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.rbac import ROLE_PERMISSIONS, Permission
from app.auth.service import AuthService
from app.config.settings import Settings
from app.models.membership import Membership, MembershipRole
from app.models.organization import Organization
from app.models.user import User
from app.services.invitation_service import InvitationService, PersonalOrganizationError
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


class TestRegisterAccountTypes:
    """AuthService.register() — personal vs business workspace creation."""

    def _service(self) -> AuthService:
        svc = AuthService(AsyncMock(), _test_settings())
        svc._user_repo = AsyncMock()
        svc._session_repo = AsyncMock()
        svc._membership_repo = AsyncMock()
        svc._org_repo = AsyncMock()
        svc._org_repo.slug_exists = AsyncMock(return_value=False)
        svc._verify_repo = AsyncMock()
        svc._email = AsyncMock()
        svc._user_repo.email_exists = AsyncMock(return_value=False)
        return svc

    @pytest.mark.asyncio
    async def test_personal_registration_creates_exactly_one_workspace(self) -> None:
        svc = self._service()
        created_orgs: list[Organization] = []

        async def _create_org(org: Organization) -> Organization:
            created_orgs.append(org)
            return org

        svc._org_repo.create = AsyncMock(side_effect=_create_org)
        svc._membership_repo.create = AsyncMock()

        _pair, _user, workspace = await svc.register(
            email="solo@example.com",
            password="correct-horse-battery-staple",
            display_name="Solo Dev",
            account_type="personal",
        )

        assert len(created_orgs) == 1
        assert created_orgs[0].is_personal is True
        assert workspace.is_personal is True

    @pytest.mark.asyncio
    async def test_business_registration_creates_personal_plus_business_workspace(self) -> None:
        svc = self._service()
        created_orgs: list[Organization] = []

        async def _create_org(org: Organization) -> Organization:
            created_orgs.append(org)
            return org

        svc._org_repo.create = AsyncMock(side_effect=_create_org)
        svc._membership_repo.create = AsyncMock()

        _pair, _user, workspace = await svc.register(
            email="founder@example.com",
            password="correct-horse-battery-staple",
            display_name="Founder",
            account_type="business",
            organization_name="Acme Inc",
        )

        assert len(created_orgs) == 2
        personal, business = created_orgs
        assert personal.is_personal is True
        assert business.is_personal is False
        assert business.name == "Acme Inc"
        # The workspace returned to the caller (and handed off to the
        # frontend) is the real business workspace, not the hidden one.
        assert workspace is business
        assert workspace.is_personal is False

    @pytest.mark.asyncio
    async def test_business_registration_falls_back_to_a_default_name(self) -> None:
        svc = self._service()
        created_orgs: list[Organization] = []

        async def _create_org(org: Organization) -> Organization:
            created_orgs.append(org)
            return org

        svc._org_repo.create = AsyncMock(side_effect=_create_org)
        svc._membership_repo.create = AsyncMock()

        _pair, _user, workspace = await svc.register(
            email="founder2@example.com",
            password="correct-horse-battery-staple",
            display_name="Founder Two",
            account_type="business",
            organization_name=None,
        )

        assert workspace.name == "Founder Two's Team"

    @pytest.mark.asyncio
    async def test_default_account_type_is_personal(self) -> None:
        svc = self._service()
        created_orgs: list[Organization] = []

        async def _create_org(org: Organization) -> Organization:
            created_orgs.append(org)
            return org

        svc._org_repo.create = AsyncMock(side_effect=_create_org)
        svc._membership_repo.create = AsyncMock()

        await svc.register(
            email="default@example.com",
            password="correct-horse-battery-staple",
            display_name="Default User",
        )

        assert len(created_orgs) == 1
        assert created_orgs[0].is_personal is True


class TestInvitationsRejectPersonalOrgs:
    @pytest.mark.asyncio
    async def test_create_invitation_refuses_a_personal_organization(self) -> None:
        svc = InvitationService(AsyncMock(), _test_settings())
        personal_org = make_org(is_personal=True)
        inviter = make_user(email="owner@example.com")

        with pytest.raises(PersonalOrganizationError):
            await svc.create_invitation(
                organization=personal_org,
                email="teammate@example.com",
                role=MembershipRole.MEMBER,
                inviter=inviter,
            )

    @pytest.mark.asyncio
    async def test_create_invitation_still_works_for_a_business_organization(self) -> None:
        svc = InvitationService(AsyncMock(), _test_settings())
        svc._membership_repo = AsyncMock()
        svc._membership_repo.get_by_org_and_email = AsyncMock(return_value=None)
        svc._repo = AsyncMock()
        svc._repo.get_pending_by_org_and_email = AsyncMock(return_value=None)
        svc._repo.create = AsyncMock(side_effect=lambda x: x)
        svc._email = AsyncMock()
        business_org = make_org(is_personal=False)
        inviter = make_user(email="owner@example.com")

        created = await svc.create_invitation(
            organization=business_org,
            email="teammate@example.com",
            role=MembershipRole.MEMBER,
            inviter=inviter,
        )
        assert created is not None


def _override_auth(app: Any, *, caller_role: MembershipRole) -> AsyncMock:
    from app.api.deps import get_db
    from app.auth.dependencies import get_current_user

    mock_user = MagicMock(spec=User)
    mock_user.email = "caller@example.com"
    mock_user.id = uuid.uuid4()
    mock_user.status = "active"
    mock_user.display_name = "Caller"

    async def mock_get_user() -> User:
        return mock_user  # type: ignore[return-value]

    mock_session = AsyncMock()

    async def mock_get_db() -> Any:
        yield mock_session

    app.dependency_overrides[get_current_user] = mock_get_user
    app.dependency_overrides[get_db] = mock_get_db
    return mock_session


def _membership(*, role: MembershipRole) -> Any:
    m = MagicMock(spec=Membership)
    m.id = uuid.uuid4()
    m.role = role
    m.organization_id = _ORG_ID
    m.user_id = uuid.uuid4()
    m.user_email = "caller@example.com"
    m.created_at = datetime.now(UTC)
    return m


class TestApiGuardsForPersonalOrganizations:
    """A personal org's sole member is always OWNER, so every one of these
    calls clears the RequirePermission check — the 400 comes entirely from
    the new is_personal guard inside each endpoint, not from RBAC."""

    @pytest.mark.asyncio
    async def test_invite_member_rejects_personal_org(self, app: Any) -> None:
        _override_auth(app, caller_role=MembershipRole.OWNER)
        personal_org = make_org(is_personal=True)
        try:
            with (
                patch.multiple(
                    "app.auth.dependencies",
                    OrganizationRepository=MagicMock(
                        return_value=MagicMock(get=AsyncMock(return_value=personal_org))
                    ),
                    MembershipRepository=MagicMock(
                        return_value=MagicMock(
                            get_by_org_and_email=AsyncMock(
                                return_value=_membership(role=MembershipRole.OWNER)
                            )
                        )
                    ),
                ),
                patch(
                    "app.api.v1.organizations.OrganizationRepository",
                    return_value=MagicMock(get=AsyncMock(return_value=personal_org)),
                ),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(
                        f"/v1/organizations/{_ORG_ID}/members",
                        json={"email": "new@example.com", "role": "member"},
                    )
            assert resp.status_code == 400
            assert "cannot invite" in resp.json()["detail"].lower()
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_rename_rejects_personal_org(self, app: Any) -> None:
        _override_auth(app, caller_role=MembershipRole.OWNER)
        personal_org = make_org(is_personal=True)
        try:
            with (
                patch.multiple(
                    "app.auth.dependencies",
                    OrganizationRepository=MagicMock(
                        return_value=MagicMock(get=AsyncMock(return_value=personal_org))
                    ),
                    MembershipRepository=MagicMock(
                        return_value=MagicMock(
                            get_by_org_and_email=AsyncMock(
                                return_value=_membership(role=MembershipRole.OWNER)
                            )
                        )
                    ),
                ),
                patch(
                    "app.api.v1.organizations.OrganizationRepository",
                    return_value=MagicMock(get=AsyncMock(return_value=personal_org)),
                ),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.patch(f"/v1/organizations/{_ORG_ID}", json={"name": "New Name"})
            assert resp.status_code == 400
            assert "cannot be renamed" in resp.json()["detail"].lower()
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_create_invitation_endpoint_rejects_personal_org(self, app: Any) -> None:
        _override_auth(app, caller_role=MembershipRole.OWNER)
        personal_org = make_org(is_personal=True)
        try:
            with (
                patch.multiple(
                    "app.auth.dependencies",
                    OrganizationRepository=MagicMock(
                        return_value=MagicMock(get=AsyncMock(return_value=personal_org))
                    ),
                    MembershipRepository=MagicMock(
                        return_value=MagicMock(
                            get_by_org_and_email=AsyncMock(
                                return_value=_membership(role=MembershipRole.OWNER)
                            )
                        )
                    ),
                ),
                patch(
                    "app.api.v1.organizations.OrganizationRepository",
                    return_value=MagicMock(get=AsyncMock(return_value=personal_org)),
                ),
                patch(
                    "app.api.v1.organizations._get_invitation_rate_limiter",
                    return_value=AsyncMock(
                        check_and_record=AsyncMock(
                            return_value=MagicMock(allowed=True, retry_after_seconds=0)
                        )
                    ),
                ),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(
                        f"/v1/organizations/{_ORG_ID}/invitations",
                        json={"email": "new@example.com", "role": "member"},
                    )
            assert resp.status_code == 400
            assert "cannot invite" in resp.json()["detail"].lower()
        finally:
            app.dependency_overrides.clear()


class TestAccountDeletionCascade:
    """AuthService.delete_account()'s cascade for a solely-owned org."""

    @pytest.mark.asyncio
    async def test_cascade_soft_deletes_every_dependent_resource(self) -> None:
        settings = _test_settings()
        svc = AuthService(AsyncMock(), settings)
        user = make_user(email="solo@example.com", password_hash="hashed")
        org = make_org(is_personal=True)
        membership = MagicMock(spec=Membership)
        membership.role = MembershipRole.OWNER
        membership.organization_id = org.id
        membership.organization = org
        membership.user_email = user.email

        svc._membership_repo = AsyncMock()
        svc._membership_repo.list_by_user_email_with_orgs = AsyncMock(return_value=[membership])
        svc._membership_repo.list_by_org_with_users = AsyncMock(return_value=[membership])
        svc._org_repo = AsyncMock()
        svc._org_repo.get = AsyncMock(return_value=org)
        svc._org_repo.soft_delete = AsyncMock()
        svc._user_repo = AsyncMock()
        svc._session_repo = AsyncMock()

        project = MagicMock()
        connection = MagicMock()
        budget = MagicMock()
        api_key = MagicMock()
        invitation = MagicMock()

        with (
            patch("app.auth.service.verify_password", return_value=True),
            patch(
                "app.auth.service.ProjectRepository",
                return_value=MagicMock(
                    list_by_org=AsyncMock(return_value=MagicMock(items=[project])),
                    soft_delete=AsyncMock(),
                ),
            ) as mock_project_repo,
            patch(
                "app.auth.service.ProviderConnectionRepository",
                return_value=MagicMock(
                    list_by_org=AsyncMock(return_value=MagicMock(items=[connection])),
                    soft_delete=AsyncMock(),
                ),
            ) as mock_conn_repo,
            patch(
                "app.auth.service.BudgetRepository",
                return_value=MagicMock(
                    list_for_org=AsyncMock(return_value=[budget]),
                    soft_delete=AsyncMock(),
                ),
            ) as mock_budget_repo,
            patch(
                "app.auth.service.OrganizationApiKeyRepository",
                return_value=MagicMock(
                    list=AsyncMock(return_value=[api_key]),
                    soft_delete=AsyncMock(),
                ),
            ) as mock_key_repo,
            patch(
                "app.auth.service.InvitationRepository",
                return_value=MagicMock(
                    list_pending_by_org=AsyncMock(return_value=[invitation]),
                ),
            ),
        ):
            await svc.delete_account(user=user, password="correct-horse")

        mock_project_repo.return_value.soft_delete.assert_awaited_once_with(
            project, deleted_by=user.id
        )
        mock_conn_repo.return_value.soft_delete.assert_awaited_once_with(
            connection, deleted_by=user.id
        )
        mock_budget_repo.return_value.soft_delete.assert_awaited_once_with(
            budget, deleted_by=user.id
        )
        mock_key_repo.return_value.soft_delete.assert_awaited_once_with(api_key, deleted_by=user.id)
        assert invitation.status.name == "CANCELLED"
        svc._org_repo.soft_delete.assert_awaited_once_with(org, deleted_by=user.id)
        svc._user_repo.soft_delete.assert_awaited_once_with(user, deleted_by=user.id)
        svc._session_repo.revoke_all_for_user.assert_awaited_once_with(user.id)


class TestPersonalOrgRbacIsStructural:
    """A personal org's sole member is always OWNER by construction
    (AuthService._create_workspace) — OWNER already holds every Permission
    (`_OWNER_PERMS = frozenset(Permission)`), so no special-cased bypass
    branch is required anywhere in app.auth.rbac for this to work."""

    def test_owner_role_grants_every_permission(self) -> None:
        for permission in Permission:
            assert permission in ROLE_PERMISSIONS[MembershipRole.OWNER]

    def test_owner_permission_set_is_the_full_permission_enum(self) -> None:
        assert ROLE_PERMISSIONS[MembershipRole.OWNER] == frozenset(Permission)
