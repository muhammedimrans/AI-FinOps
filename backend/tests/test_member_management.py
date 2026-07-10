"""Tests for organization member management (EP-13).

Covers:
  - MembershipRepository.list_by_org_with_users / link_pending_by_email
  - AuthService.login linking pending invitations
  - GET/POST/PATCH/DELETE /v1/organizations/{org_id}/members
  - Privilege-escalation guard (only an OWNER can grant OWNER)
  - Last-owner guard (cannot demote/remove the only owner)

All tests are hermetic — no network calls, no real database.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.models.membership import Membership, MembershipRole
from app.models.user import User
from tests.conftest import make_membership, make_user

_ORG_ID = uuid.uuid4()


# ══════════════════════════════════════════════════════════════════════════════
# Repository tests
# ══════════════════════════════════════════════════════════════════════════════


class TestListByOrgWithUsers:
    @pytest.mark.asyncio
    async def test_returns_memberships_with_user_loaded(self) -> None:
        from app.repositories.membership_repository import MembershipRepository

        user = make_user(email="alice@example.com")
        mem = make_membership(org_id=_ORG_ID, user_email="alice@example.com")
        mem.__dict__["user"] = user

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mem]
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = MembershipRepository(mock_session)
        result = await repo.list_by_org_with_users(_ORG_ID)
        assert len(result) == 1
        assert result[0].user.email == "alice@example.com"

    @pytest.mark.asyncio
    async def test_empty_org_returns_empty_list(self) -> None:
        from app.repositories.membership_repository import MembershipRepository

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = MembershipRepository(mock_session)
        result = await repo.list_by_org_with_users(_ORG_ID)
        assert result == []


class TestLinkPendingByEmail:
    @pytest.mark.asyncio
    async def test_returns_rowcount(self) -> None:
        from app.repositories.membership_repository import MembershipRepository

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 2
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = MembershipRepository(mock_session)
        count = await repo.link_pending_by_email("bob@example.com", uuid.uuid4())
        assert count == 2

    @pytest.mark.asyncio
    async def test_zero_rowcount_returns_zero_not_none(self) -> None:
        from app.repositories.membership_repository import MembershipRepository

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = MembershipRepository(mock_session)
        count = await repo.link_pending_by_email("nobody@example.com", uuid.uuid4())
        assert count == 0


class TestLoginLinksPendingInvitations:
    @pytest.mark.asyncio
    async def test_login_calls_link_pending_by_email(self) -> None:
        from app.auth.password import hash_password
        from app.auth.service import AuthService
        from app.config.settings import Settings

        settings = Settings(
            app_secret_key="a" * 32,
            jwt_secret="j" * 32,
        )
        password = "correct-horse-battery-staple"
        user = make_user(
            email="carol@example.com", password_hash=hash_password(password), email_verified=True
        )

        svc = AuthService(AsyncMock(), settings)
        svc._user_repo = AsyncMock()
        svc._user_repo.get_by_email.return_value = user
        svc._session_repo = AsyncMock()
        svc._membership_repo = AsyncMock()

        await svc.login(email=user.email, password=password)

        svc._membership_repo.link_pending_by_email.assert_awaited_once_with(user.email, user.id)


# ══════════════════════════════════════════════════════════════════════════════
# API endpoint tests
# ══════════════════════════════════════════════════════════════════════════════


def _override_auth(
    app: Any, *, caller_role: MembershipRole, caller_email: str = "caller@example.com"
) -> Any:
    """Override auth so the caller is a member of _ORG_ID with the given role."""
    from app.api.deps import get_db
    from app.auth.dependencies import get_current_user
    from app.models.organization import Organization, OrganizationStatus

    mock_user = MagicMock(spec=User)
    mock_user.email = caller_email
    mock_user.status = "active"

    async def mock_get_user() -> User:
        return mock_user  # type: ignore[return-value]

    mock_session = AsyncMock()

    async def mock_get_db() -> Any:
        yield mock_session

    app.dependency_overrides[get_current_user] = mock_get_user
    app.dependency_overrides[get_db] = mock_get_db

    org = MagicMock(spec=Organization)
    org.id = _ORG_ID
    org.status = OrganizationStatus.ACTIVE

    caller_membership = MagicMock(spec=Membership)
    caller_membership.role = caller_role

    org_repo = MagicMock()
    org_repo.get = AsyncMock(return_value=org)
    mem_repo_for_org_lookup = MagicMock()
    mem_repo_for_org_lookup.get_by_org_and_email = AsyncMock(return_value=caller_membership)

    return mock_session, org_repo, mem_repo_for_org_lookup


class TestListMembersEndpoint:
    @pytest.mark.asyncio
    async def test_unauthenticated_is_401(self, app: Any) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get(f"/v1/organizations/{_ORG_ID}/members")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_member_can_list(self, app: Any) -> None:
        _session, org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.VIEWER)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                user = make_user(email="alice@example.com")
                mem = make_membership(
                    org_id=_ORG_ID, user_email="alice@example.com", role=MembershipRole.OWNER
                )
                mem.created_at = datetime.now(UTC)
                mem.user_id = user.id
                mem.__dict__["user"] = user
                with patch(
                    "app.api.v1.organizations.MembershipRepository.list_by_org_with_users",
                    new=AsyncMock(return_value=[mem]),
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.get(f"/v1/organizations/{_ORG_ID}/members")
            assert resp.status_code == 200
            body = resp.json()
            assert body["total"] == 1
            assert body["members"][0]["email"] == "alice@example.com"
            assert body["members"][0]["status"] == "active"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_non_member_is_403(self, app: Any) -> None:
        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user
        from app.models.organization import Organization, OrganizationStatus

        mock_user = MagicMock(spec=User)
        mock_user.email = "outsider@example.com"

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        async def mock_get_db() -> Any:
            yield AsyncMock()

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_db] = mock_get_db

        org = MagicMock(spec=Organization)
        org.id = _ORG_ID
        org.status = OrganizationStatus.ACTIVE
        org_repo = MagicMock()
        org_repo.get = AsyncMock(return_value=org)
        mem_repo = MagicMock()
        mem_repo.get_by_org_and_email = AsyncMock(return_value=None)

        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.get(f"/v1/organizations/{_ORG_ID}/members")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()


class TestInviteMemberEndpoint:
    @pytest.mark.asyncio
    async def test_viewer_cannot_invite(self, app: Any) -> None:
        _override_auth(app, caller_role=MembershipRole.VIEWER)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(
                    return_value=MagicMock(get=AsyncMock(return_value=_active_org()))
                ),
                MembershipRepository=MagicMock(
                    return_value=MagicMock(
                        get_by_org_and_email=AsyncMock(
                            return_value=_membership(role=MembershipRole.VIEWER)
                        )
                    )
                ),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(
                        f"/v1/organizations/{_ORG_ID}/members",
                        json={"email": "new@example.com", "role": "member"},
                    )
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_admin_cannot_grant_owner_role(self, app: Any) -> None:
        """Privilege-escalation guard: an ADMIN must not be able to mint a co-equal OWNER."""
        _override_auth(app, caller_role=MembershipRole.ADMIN)
        try:
            with (
                patch.multiple(
                    "app.auth.dependencies",
                    OrganizationRepository=MagicMock(
                        return_value=MagicMock(get=AsyncMock(return_value=_active_org()))
                    ),
                    MembershipRepository=MagicMock(
                        return_value=MagicMock(
                            get_by_org_and_email=AsyncMock(
                                return_value=_membership(role=MembershipRole.ADMIN)
                            )
                        )
                    ),
                ),
                patch(
                    "app.api.v1.organizations.OrganizationRepository",
                    return_value=MagicMock(get=AsyncMock(return_value=_active_org())),
                ),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(
                        f"/v1/organizations/{_ORG_ID}/members",
                        json={"email": "new@example.com", "role": "owner"},
                    )
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_owner_can_grant_owner_role(self, app: Any) -> None:
        _override_auth(app, caller_role=MembershipRole.OWNER)
        try:
            with (
                patch.multiple(
                    "app.auth.dependencies",
                    OrganizationRepository=MagicMock(
                        return_value=MagicMock(get=AsyncMock(return_value=_active_org()))
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
                    return_value=MagicMock(get=AsyncMock(return_value=_active_org())),
                ),
            ):
                created = make_membership(
                    org_id=_ORG_ID, user_email="new@example.com", role=MembershipRole.OWNER
                )
                created.created_at = datetime.now(UTC)
                with (
                    patch(
                        "app.api.v1.organizations.MembershipRepository.get_by_org_and_email",
                        new=AsyncMock(return_value=None),
                    ),
                    patch(
                        "app.api.v1.organizations.MembershipRepository.create",
                        new=AsyncMock(return_value=created),
                    ),
                    patch(
                        "app.api.v1.organizations.UserRepository.get_by_email",
                        new=AsyncMock(return_value=None),
                    ),
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.post(
                            f"/v1/organizations/{_ORG_ID}/members",
                            json={"email": "new@example.com", "role": "owner"},
                        )
            assert resp.status_code == 201
            assert resp.json()["role"] == "owner"
            assert resp.json()["status"] == "invited"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_duplicate_member_is_409(self, app: Any) -> None:
        _override_auth(app, caller_role=MembershipRole.OWNER)
        try:
            with (
                patch.multiple(
                    "app.auth.dependencies",
                    OrganizationRepository=MagicMock(
                        return_value=MagicMock(get=AsyncMock(return_value=_active_org()))
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
                    return_value=MagicMock(get=AsyncMock(return_value=_active_org())),
                ),
            ):
                with patch(
                    "app.api.v1.organizations.MembershipRepository.get_by_org_and_email",
                    new=AsyncMock(return_value=_membership(role=MembershipRole.MEMBER)),
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.post(
                            f"/v1/organizations/{_ORG_ID}/members",
                            json={"email": "existing@example.com", "role": "member"},
                        )
            assert resp.status_code == 409
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_invalid_role_is_422(self, app: Any) -> None:
        _override_auth(app, caller_role=MembershipRole.OWNER)
        try:
            with (
                patch.multiple(
                    "app.auth.dependencies",
                    OrganizationRepository=MagicMock(
                        return_value=MagicMock(get=AsyncMock(return_value=_active_org()))
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
                    return_value=MagicMock(get=AsyncMock(return_value=_active_org())),
                ),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(
                        f"/v1/organizations/{_ORG_ID}/members",
                        json={"email": "new@example.com", "role": "superadmin"},
                    )
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.clear()


class TestUpdateMemberRoleEndpoint:
    @pytest.mark.asyncio
    async def test_cannot_demote_last_owner(self, app: Any) -> None:
        _override_auth(app, caller_role=MembershipRole.OWNER)
        membership_id = uuid.uuid4()
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(
                    return_value=MagicMock(get=AsyncMock(return_value=_active_org()))
                ),
                MembershipRepository=MagicMock(
                    return_value=MagicMock(
                        get_by_org_and_email=AsyncMock(
                            return_value=_membership(role=MembershipRole.OWNER)
                        )
                    )
                ),
            ):
                target = _membership(role=MembershipRole.OWNER)
                target.id = membership_id
                target.organization_id = _ORG_ID
                with (
                    patch(
                        "app.api.v1.organizations.MembershipRepository.get",
                        new=AsyncMock(return_value=target),
                    ),
                    patch(
                        "app.api.v1.organizations.MembershipRepository.count",
                        new=AsyncMock(return_value=1),
                    ),
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.patch(
                            f"/v1/organizations/{_ORG_ID}/members/{membership_id}",
                            json={"role": "admin"},
                        )
            assert resp.status_code == 409
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_can_demote_owner_when_multiple_owners_exist(self, app: Any) -> None:
        _override_auth(app, caller_role=MembershipRole.OWNER)
        membership_id = uuid.uuid4()
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(
                    return_value=MagicMock(get=AsyncMock(return_value=_active_org()))
                ),
                MembershipRepository=MagicMock(
                    return_value=MagicMock(
                        get_by_org_and_email=AsyncMock(
                            return_value=_membership(role=MembershipRole.OWNER)
                        )
                    )
                ),
            ):
                target = _membership(role=MembershipRole.OWNER)
                target.id = membership_id
                target.organization_id = _ORG_ID
                updated = _membership(role=MembershipRole.ADMIN)
                updated.id = membership_id
                updated.user_id = None
                updated.created_at = datetime.now(UTC)
                with (
                    patch(
                        "app.api.v1.organizations.MembershipRepository.get",
                        new=AsyncMock(return_value=target),
                    ),
                    patch(
                        "app.api.v1.organizations.MembershipRepository.count",
                        new=AsyncMock(return_value=2),
                    ),
                    patch(
                        "app.api.v1.organizations.MembershipRepository.update",
                        new=AsyncMock(return_value=updated),
                    ),
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.patch(
                            f"/v1/organizations/{_ORG_ID}/members/{membership_id}",
                            json={"role": "admin"},
                        )
            assert resp.status_code == 200
            assert resp.json()["role"] == "admin"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_member_not_found_is_404(self, app: Any) -> None:
        _override_auth(app, caller_role=MembershipRole.OWNER)
        membership_id = uuid.uuid4()
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(
                    return_value=MagicMock(get=AsyncMock(return_value=_active_org()))
                ),
                MembershipRepository=MagicMock(
                    return_value=MagicMock(
                        get_by_org_and_email=AsyncMock(
                            return_value=_membership(role=MembershipRole.OWNER)
                        )
                    )
                ),
            ):
                with patch(
                    "app.api.v1.organizations.MembershipRepository.get",
                    new=AsyncMock(return_value=None),
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.patch(
                            f"/v1/organizations/{_ORG_ID}/members/{membership_id}",
                            json={"role": "admin"},
                        )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()


class TestRemoveMemberEndpoint:
    @pytest.mark.asyncio
    async def test_cannot_remove_last_owner(self, app: Any) -> None:
        _override_auth(app, caller_role=MembershipRole.OWNER)
        membership_id = uuid.uuid4()
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(
                    return_value=MagicMock(get=AsyncMock(return_value=_active_org()))
                ),
                MembershipRepository=MagicMock(
                    return_value=MagicMock(
                        get_by_org_and_email=AsyncMock(
                            return_value=_membership(role=MembershipRole.OWNER)
                        )
                    )
                ),
            ):
                target = _membership(role=MembershipRole.OWNER)
                target.id = membership_id
                target.organization_id = _ORG_ID
                with (
                    patch(
                        "app.api.v1.organizations.MembershipRepository.get",
                        new=AsyncMock(return_value=target),
                    ),
                    patch(
                        "app.api.v1.organizations.MembershipRepository.count",
                        new=AsyncMock(return_value=1),
                    ),
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.delete(
                            f"/v1/organizations/{_ORG_ID}/members/{membership_id}"
                        )
            assert resp.status_code == 409
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_can_remove_non_owner_member(self, app: Any) -> None:
        _override_auth(app, caller_role=MembershipRole.ADMIN)
        membership_id = uuid.uuid4()
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(
                    return_value=MagicMock(get=AsyncMock(return_value=_active_org()))
                ),
                MembershipRepository=MagicMock(
                    return_value=MagicMock(
                        get_by_org_and_email=AsyncMock(
                            return_value=_membership(role=MembershipRole.ADMIN)
                        )
                    )
                ),
            ):
                target = _membership(role=MembershipRole.MEMBER)
                target.id = membership_id
                target.organization_id = _ORG_ID
                with (
                    patch(
                        "app.api.v1.organizations.MembershipRepository.get",
                        new=AsyncMock(return_value=target),
                    ),
                    patch(
                        "app.api.v1.organizations.MembershipRepository.soft_delete",
                        new=AsyncMock(return_value=target),
                    ),
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.delete(
                            f"/v1/organizations/{_ORG_ID}/members/{membership_id}"
                        )
            assert resp.status_code == 204
        finally:
            app.dependency_overrides.clear()


def _active_org() -> Any:
    from app.models.organization import Organization, OrganizationStatus

    org = MagicMock(spec=Organization)
    org.id = _ORG_ID
    org.status = OrganizationStatus.ACTIVE
    # EP-25.1: every call site here represents a normal, invitable business
    # org — invite_member()'s new is_personal guard needs this set
    # explicitly, since a MagicMock attribute is truthy by default.
    org.is_personal = False
    return org


def _membership(*, role: MembershipRole) -> Any:
    m = MagicMock(spec=Membership)
    m.role = role
    m.organization_id = _ORG_ID
    m.user_id = uuid.uuid4()
    m.user_email = "member@example.com"
    m.created_at = datetime.now(UTC)
    return m
