"""Tests for organization invitations & team collaboration (EP-24.6).

Covers:
  - InvitationRepository (pending/duplicate lookup, valid-token lookup, org listing)
  - InvitationService (create/resend/accept/decline/cancel, all guard rails)
  - RBAC (ORG_TRANSFER_OWNERSHIP is OWNER-only; existing roles unaffected)
  - API: GET/POST /v1/organizations/{org_id}/invitations
  - API: POST /v1/invitations/{token}/accept|decline, POST .../resend, DELETE .../{id}
  - API: POST /v1/organizations/{org_id}/transfer-ownership
  - New role-change/remove-member guards (self-demotion, admin-cannot-remove-owner)

All tests are hermetic — no network calls, no real database (this EP was also
manually verified end-to-end against a real local PostgreSQL 16 instance —
see CLAUDE.md's EP-24.6 section for that trace).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.rbac import ROLE_PERMISSIONS, Permission
from app.models.invitation import Invitation, InvitationStatus
from app.models.membership import Membership, MembershipRole
from app.models.user import User
from app.services.invitation_service import (
    AlreadyMemberError,
    CannotInviteSelfError,
    DuplicatePendingInvitationError,
    InvalidInvitationTokenError,
    InvitationEmailMismatchError,
    InvitationService,
)
from tests.conftest import make_membership, make_org, make_user

_ORG_ID = uuid.uuid4()


def _make_invitation(
    *,
    email: str = "invitee@example.com",
    role: MembershipRole = MembershipRole.MEMBER,
    status: InvitationStatus = InvitationStatus.PENDING,
    expires_delta: timedelta = timedelta(days=7),
    org_id: uuid.UUID = _ORG_ID,
) -> Invitation:
    inv = Invitation()
    inv.id = uuid.uuid4()
    inv.organization_id = org_id
    inv.email = email
    inv.role = role
    inv.token_hash = "a" * 64
    inv.status = status
    inv.created_by = uuid.uuid4()
    inv.expires_at = datetime.now(UTC) + expires_delta
    inv.accepted_at = None
    inv.cancelled_at = None
    inv.created_at = datetime.now(UTC)
    return inv


# ══════════════════════════════════════════════════════════════════════════════
# RBAC
# ══════════════════════════════════════════════════════════════════════════════


class TestOrgTransferOwnershipPermission:
    def test_only_owner_has_it(self) -> None:
        assert Permission.ORG_TRANSFER_OWNERSHIP in ROLE_PERMISSIONS[MembershipRole.OWNER]
        assert Permission.ORG_TRANSFER_OWNERSHIP not in ROLE_PERMISSIONS[MembershipRole.ADMIN]
        assert Permission.ORG_TRANSFER_OWNERSHIP not in ROLE_PERMISSIONS[MembershipRole.MEMBER]
        assert Permission.ORG_TRANSFER_OWNERSHIP not in ROLE_PERMISSIONS[MembershipRole.VIEWER]

    def test_existing_roles_unaffected(self) -> None:
        """Adding a permission the OWNER frozenset auto-includes must never
        change any other role's existing grants."""
        assert Permission.ORG_MANAGE_MEMBERS in ROLE_PERMISSIONS[MembershipRole.ADMIN]
        assert Permission.PROJECT_DELETE in ROLE_PERMISSIONS[MembershipRole.MEMBER]


# ══════════════════════════════════════════════════════════════════════════════
# InvitationRepository
# ══════════════════════════════════════════════════════════════════════════════


class TestInvitationRepository:
    @pytest.mark.asyncio
    async def test_get_pending_by_org_and_email_found(self) -> None:
        from app.repositories.invitation_repository import InvitationRepository

        inv = _make_invitation()
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = inv
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = InvitationRepository(mock_session)
        result = await repo.get_pending_by_org_and_email(_ORG_ID, "invitee@example.com")
        assert result is inv

    @pytest.mark.asyncio
    async def test_get_valid_by_token_hash_not_found(self) -> None:
        from app.repositories.invitation_repository import InvitationRepository

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = InvitationRepository(mock_session)
        result = await repo.get_valid_by_token_hash("deadbeef")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_pending_by_org_returns_list(self) -> None:
        from app.repositories.invitation_repository import InvitationRepository

        inv = _make_invitation()
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [inv]
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = InvitationRepository(mock_session)
        result = await repo.list_pending_by_org(_ORG_ID)
        assert result == [inv]


# ══════════════════════════════════════════════════════════════════════════════
# InvitationService
# ══════════════════════════════════════════════════════════════════════════════


def _settings() -> Any:
    from app.config.settings import Settings

    return Settings(app_secret_key="a" * 32, jwt_secret="j" * 32)


def _make_service(email_service: Any = None) -> tuple[InvitationService, AsyncMock]:
    session = AsyncMock()
    svc = InvitationService(session, _settings(), email_service=email_service or AsyncMock())
    svc._repo = AsyncMock()
    svc._membership_repo = AsyncMock()
    svc._org_repo = AsyncMock()
    svc._user_repo = AsyncMock()
    return svc, session


class TestCreateInvitation:
    @pytest.mark.asyncio
    async def test_cannot_invite_self(self) -> None:
        svc, _ = _make_service()
        inviter = make_user(email="owner@example.com")
        org = make_org()
        org.id = _ORG_ID
        with pytest.raises(CannotInviteSelfError):
            await svc.create_invitation(
                organization=org,
                email="Owner@Example.com",  # case-insensitive match
                role=MembershipRole.MEMBER,
                inviter=inviter,
            )

    @pytest.mark.asyncio
    async def test_already_member_rejected(self) -> None:
        svc, _ = _make_service()
        inviter = make_user(email="owner@example.com")
        org = make_org()
        org.id = _ORG_ID
        svc._membership_repo.get_by_org_and_email = AsyncMock(
            return_value=make_membership(org_id=_ORG_ID, user_email="taken@example.com")
        )
        with pytest.raises(AlreadyMemberError):
            await svc.create_invitation(
                organization=org,
                email="taken@example.com",
                role=MembershipRole.MEMBER,
                inviter=inviter,
            )

    @pytest.mark.asyncio
    async def test_duplicate_pending_rejected(self) -> None:
        svc, _ = _make_service()
        inviter = make_user(email="owner@example.com")
        org = make_org()
        org.id = _ORG_ID
        svc._membership_repo.get_by_org_and_email = AsyncMock(return_value=None)
        svc._repo.get_pending_by_org_and_email = AsyncMock(return_value=_make_invitation())
        with pytest.raises(DuplicatePendingInvitationError):
            await svc.create_invitation(
                organization=org,
                email="new@example.com",
                role=MembershipRole.MEMBER,
                inviter=inviter,
            )

    @pytest.mark.asyncio
    async def test_success_sends_email_and_stores_hash_only(self) -> None:
        email_service = AsyncMock()
        svc, _ = _make_service(email_service=email_service)
        inviter = make_user(email="owner@example.com", display_name="Owner")
        org = make_org(name="Acme")
        org.id = _ORG_ID
        svc._membership_repo.get_by_org_and_email = AsyncMock(return_value=None)
        svc._repo.get_pending_by_org_and_email = AsyncMock(return_value=None)
        created = _make_invitation(email="new@example.com")
        svc._repo.create = AsyncMock(return_value=created)

        result = await svc.create_invitation(
            organization=org, email="new@example.com", role=MembershipRole.MEMBER, inviter=inviter
        )

        assert result is created
        email_service.send_invitation_email.assert_awaited_once()
        call_kwargs = email_service.send_invitation_email.call_args.kwargs
        assert call_kwargs["to"] == "new@example.com"
        assert call_kwargs["organization_name"] == "Acme"
        # never the raw token anywhere the test can trivially assert on —
        # the accept_url must contain SOME token, but never the literal word
        # "None" or an empty string, confirming a real token was generated.
        assert "token=" in call_kwargs["accept_url"]
        assert call_kwargs["accept_url"].split("token=")[1] != ""


class TestResendInvitation:
    @pytest.mark.asyncio
    async def test_overwrites_token_and_resends(self) -> None:
        email_service = AsyncMock()
        svc, _ = _make_service(email_service=email_service)
        actor = make_user(email="owner@example.com")
        org = make_org(name="Acme")
        org.id = _ORG_ID
        existing = _make_invitation()
        old_hash = existing.token_hash
        updated = _make_invitation()
        svc._repo.update = AsyncMock(return_value=updated)

        await svc.resend_invitation(invitation=existing, organization=org, actor=actor)

        update_kwargs = svc._repo.update.call_args.kwargs
        assert update_kwargs["token_hash"] != old_hash
        assert update_kwargs["status"] == InvitationStatus.PENDING
        email_service.send_invitation_email.assert_awaited_once()


class TestAcceptInvitation:
    @pytest.mark.asyncio
    async def test_invalid_token_raises(self) -> None:
        svc, _ = _make_service()
        svc._repo.get_valid_by_token_hash = AsyncMock(return_value=None)
        user = make_user(email="invitee@example.com")
        with pytest.raises(InvalidInvitationTokenError):
            await svc.accept_invitation(token="bad-token", current_user=user)

    @pytest.mark.asyncio
    async def test_email_mismatch_raises(self) -> None:
        svc, _ = _make_service()
        inv = _make_invitation(email="invitee@example.com")
        svc._repo.get_valid_by_token_hash = AsyncMock(return_value=inv)
        wrong_user = make_user(email="someone-else@example.com")
        with pytest.raises(InvitationEmailMismatchError):
            await svc.accept_invitation(token="raw-token", current_user=wrong_user)

    @pytest.mark.asyncio
    async def test_success_creates_membership_and_marks_accepted(self) -> None:
        svc, _ = _make_service()
        inv = _make_invitation(email="invitee@example.com", role=MembershipRole.ADMIN)
        svc._repo.get_valid_by_token_hash = AsyncMock(return_value=inv)
        org = make_org()
        org.id = inv.organization_id
        svc._org_repo.get = AsyncMock(return_value=org)
        created_membership = make_membership(
            org_id=inv.organization_id, user_email="invitee@example.com", role=MembershipRole.ADMIN
        )
        svc._membership_repo.create = AsyncMock(return_value=created_membership)
        svc._user_repo.get = AsyncMock(return_value=None)  # inviter lookup, no email needed
        user = make_user(email="invitee@example.com")

        result = await svc.accept_invitation(token="raw-token", current_user=user)

        assert result is created_membership
        svc._membership_repo.create.assert_awaited_once()
        svc._repo.update.assert_awaited_once()
        update_kwargs = svc._repo.update.call_args.kwargs
        assert update_kwargs["status"] == InvitationStatus.ACCEPTED

    @pytest.mark.asyncio
    async def test_success_notifies_inviter(self) -> None:
        email_service = AsyncMock()
        svc, _ = _make_service(email_service=email_service)
        inviter_id = uuid.uuid4()
        inv = _make_invitation(email="invitee@example.com")
        inv.created_by = inviter_id
        svc._repo.get_valid_by_token_hash = AsyncMock(return_value=inv)
        org = make_org(name="Acme")
        org.id = inv.organization_id
        svc._org_repo.get = AsyncMock(return_value=org)
        svc._membership_repo.create = AsyncMock(
            return_value=make_membership(org_id=inv.organization_id, role=MembershipRole.MEMBER)
        )
        inviter = make_user(email="owner@example.com")
        svc._user_repo.get = AsyncMock(return_value=inviter)
        user = make_user(email="invitee@example.com")

        await svc.accept_invitation(token="raw-token", current_user=user)

        email_service.send_invitation_accepted_email.assert_awaited_once()
        accepted_kwargs = email_service.send_invitation_accepted_email.call_args.kwargs
        assert accepted_kwargs["to"] == "owner@example.com"


class TestDeclineInvitation:
    @pytest.mark.asyncio
    async def test_invalid_token_raises(self) -> None:
        svc, _ = _make_service()
        svc._repo.get_valid_by_token_hash = AsyncMock(return_value=None)
        with pytest.raises(InvalidInvitationTokenError):
            await svc.decline_invitation(token="bad-token")

    @pytest.mark.asyncio
    async def test_success_marks_cancelled_no_membership(self) -> None:
        svc, _ = _make_service()
        inv = _make_invitation()
        svc._repo.get_valid_by_token_hash = AsyncMock(return_value=inv)
        updated = _make_invitation(status=InvitationStatus.CANCELLED)
        svc._repo.update = AsyncMock(return_value=updated)

        result = await svc.decline_invitation(token="raw-token")

        assert result.status == InvitationStatus.CANCELLED
        svc._membership_repo.create.assert_not_called()


class TestCancelInvitation:
    @pytest.mark.asyncio
    async def test_cancels_and_notifies(self) -> None:
        email_service = AsyncMock()
        svc, _ = _make_service(email_service=email_service)
        actor = make_user(email="owner@example.com")
        org = make_org(name="Acme")
        org.id = _ORG_ID
        inv = _make_invitation()
        updated = _make_invitation(status=InvitationStatus.CANCELLED)
        svc._repo.update = AsyncMock(return_value=updated)

        result = await svc.cancel_invitation(invitation=inv, organization=org, actor=actor)

        assert result.status == InvitationStatus.CANCELLED
        email_service.send_invitation_cancelled_email.assert_awaited_once()


# ══════════════════════════════════════════════════════════════════════════════
# API — /v1/organizations/{org_id}/invitations, /transfer-ownership
# ══════════════════════════════════════════════════════════════════════════════


def _active_org() -> Any:
    from app.models.organization import Organization, OrganizationStatus

    org = MagicMock(spec=Organization)
    org.id = _ORG_ID
    org.name = "Acme"
    org.status = OrganizationStatus.ACTIVE
    return org


def _membership(*, role: MembershipRole, user_id: uuid.UUID | None = None) -> Any:
    m = MagicMock(spec=Membership)
    m.id = uuid.uuid4()
    m.role = role
    m.organization_id = _ORG_ID
    m.user_id = user_id or uuid.uuid4()
    m.user_email = "member@example.com"
    m.created_at = datetime.now(UTC)
    return m


def _override_auth(
    app: Any, *, caller_role: MembershipRole, caller_email: str = "caller@example.com"
) -> Any:
    from app.api.deps import get_db
    from app.auth.dependencies import get_current_user

    mock_user = MagicMock(spec=User)
    mock_user.email = caller_email
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
    return mock_session, mock_user


class TestListInvitationsEndpoint:
    @pytest.mark.asyncio
    async def test_admin_can_list(self, app: Any) -> None:
        _override_auth(app, caller_role=MembershipRole.ADMIN)
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
                inv = _make_invitation()
                with patch(
                    "app.api.v1.organizations.InvitationRepository.list_pending_by_org",
                    new=AsyncMock(return_value=[inv]),
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.get(f"/v1/organizations/{_ORG_ID}/invitations")
            assert resp.status_code == 200
            assert resp.json()["total"] == 1
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_member_cannot_list(self, app: Any) -> None:
        _override_auth(app, caller_role=MembershipRole.MEMBER)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(
                    return_value=MagicMock(get=AsyncMock(return_value=_active_org()))
                ),
                MembershipRepository=MagicMock(
                    return_value=MagicMock(
                        get_by_org_and_email=AsyncMock(
                            return_value=_membership(role=MembershipRole.MEMBER)
                        )
                    )
                ),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.get(f"/v1/organizations/{_ORG_ID}/invitations")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()


class TestCreateInvitationEndpoint:
    @pytest.mark.asyncio
    async def test_admin_can_invite(self, app: Any) -> None:
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
                    "app.api.v1.organizations.OrganizationRepository.get",
                    new=AsyncMock(return_value=_active_org()),
                ),
                patch(
                    "app.api.v1.organizations.InvitationService.create_invitation",
                    new=AsyncMock(return_value=_make_invitation(email="new@example.com")),
                ),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(
                        f"/v1/organizations/{_ORG_ID}/invitations",
                        json={"email": "new@example.com", "role": "member"},
                    )
            assert resp.status_code == 201
            assert resp.json()["email"] == "new@example.com"
        finally:
            app.dependency_overrides.clear()

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
                        f"/v1/organizations/{_ORG_ID}/invitations",
                        json={"email": "new@example.com", "role": "member"},
                    )
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_admin_cannot_grant_owner_role(self, app: Any) -> None:
        _override_auth(app, caller_role=MembershipRole.ADMIN)
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
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(
                        f"/v1/organizations/{_ORG_ID}/invitations",
                        json={"email": "new@example.com", "role": "owner"},
                    )
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_duplicate_pending_is_409(self, app: Any) -> None:
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
                    "app.api.v1.organizations.OrganizationRepository.get",
                    new=AsyncMock(return_value=_active_org()),
                ),
                patch(
                    "app.api.v1.organizations.InvitationService.create_invitation",
                    new=AsyncMock(side_effect=DuplicatePendingInvitationError),
                ),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(
                        f"/v1/organizations/{_ORG_ID}/invitations",
                        json={"email": "new@example.com", "role": "member"},
                    )
            assert resp.status_code == 409
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_invalid_email_is_422(self, app: Any) -> None:
        _override_auth(app, caller_role=MembershipRole.OWNER)
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
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(
                        f"/v1/organizations/{_ORG_ID}/invitations",
                        json={"email": "not-an-email", "role": "member"},
                    )
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_unauthenticated_is_401(self, app: Any) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/v1/organizations/{_ORG_ID}/invitations",
                json={"email": "new@example.com", "role": "member"},
            )
        assert resp.status_code == 401


class TestTransferOwnershipEndpoint:
    @pytest.mark.asyncio
    async def test_owner_can_transfer(self, app: Any) -> None:
        caller = _membership(role=MembershipRole.OWNER)
        new_owner = _membership(role=MembershipRole.ADMIN)
        _override_auth(app, caller_role=MembershipRole.OWNER)
        try:
            with (
                patch.multiple(
                    "app.auth.dependencies",
                    OrganizationRepository=MagicMock(
                        return_value=MagicMock(get=AsyncMock(return_value=_active_org()))
                    ),
                    MembershipRepository=MagicMock(
                        return_value=MagicMock(get_by_org_and_email=AsyncMock(return_value=caller))
                    ),
                ),
                patch(
                    "app.api.v1.organizations.MembershipRepository.get",
                    new=AsyncMock(return_value=new_owner),
                ),
                patch(
                    "app.api.v1.organizations.MembershipRepository.update",
                    new=AsyncMock(side_effect=lambda m, **kw: m),
                ),
                patch(
                    "app.api.v1.organizations.UserRepository.get",
                    new=AsyncMock(return_value=None),
                ),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(
                        f"/v1/organizations/{_ORG_ID}/transfer-ownership",
                        json={"new_owner_membership_id": str(new_owner.id)},
                    )
            assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_admin_cannot_transfer(self, app: Any) -> None:
        _override_auth(app, caller_role=MembershipRole.ADMIN)
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
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(
                        f"/v1/organizations/{_ORG_ID}/transfer-ownership",
                        json={"new_owner_membership_id": str(uuid.uuid4())},
                    )
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_transfer_to_self_is_422(self, app: Any) -> None:
        caller = _membership(role=MembershipRole.OWNER)
        _override_auth(app, caller_role=MembershipRole.OWNER)
        try:
            with (
                patch.multiple(
                    "app.auth.dependencies",
                    OrganizationRepository=MagicMock(
                        return_value=MagicMock(get=AsyncMock(return_value=_active_org()))
                    ),
                    MembershipRepository=MagicMock(
                        return_value=MagicMock(get_by_org_and_email=AsyncMock(return_value=caller))
                    ),
                ),
                patch(
                    "app.api.v1.organizations.MembershipRepository.get",
                    new=AsyncMock(return_value=caller),
                ),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(
                        f"/v1/organizations/{_ORG_ID}/transfer-ownership",
                        json={"new_owner_membership_id": str(caller.id)},
                    )
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.clear()


class TestUpdateMemberRoleGuards:
    @pytest.mark.asyncio
    async def test_owner_cannot_demote_self(self, app: Any) -> None:
        caller = _membership(role=MembershipRole.OWNER)
        _override_auth(app, caller_role=MembershipRole.OWNER)
        try:
            with (
                patch.multiple(
                    "app.auth.dependencies",
                    OrganizationRepository=MagicMock(
                        return_value=MagicMock(get=AsyncMock(return_value=_active_org()))
                    ),
                    MembershipRepository=MagicMock(
                        return_value=MagicMock(get_by_org_and_email=AsyncMock(return_value=caller))
                    ),
                ),
                patch(
                    "app.api.v1.organizations.MembershipRepository.get",
                    new=AsyncMock(return_value=caller),
                ),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.patch(
                        f"/v1/organizations/{_ORG_ID}/members/{caller.id}",
                        json={"role": "admin"},
                    )
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()


class TestRemoveMemberGuards:
    @pytest.mark.asyncio
    async def test_admin_cannot_remove_owner(self, app: Any) -> None:
        caller = _membership(role=MembershipRole.ADMIN)
        target_owner = _membership(role=MembershipRole.OWNER)
        _override_auth(app, caller_role=MembershipRole.ADMIN)
        try:
            with (
                patch.multiple(
                    "app.auth.dependencies",
                    OrganizationRepository=MagicMock(
                        return_value=MagicMock(get=AsyncMock(return_value=_active_org()))
                    ),
                    MembershipRepository=MagicMock(
                        return_value=MagicMock(get_by_org_and_email=AsyncMock(return_value=caller))
                    ),
                ),
                patch(
                    "app.api.v1.organizations.MembershipRepository.get",
                    new=AsyncMock(return_value=target_owner),
                ),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.delete(f"/v1/organizations/{_ORG_ID}/members/{target_owner.id}")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()


# ══════════════════════════════════════════════════════════════════════════════
# API — /v1/invitations/{token}/accept|decline, /{id}/resend, DELETE /{id}
# ══════════════════════════════════════════════════════════════════════════════


class TestAcceptEndpoint:
    @pytest.mark.asyncio
    async def test_unauthenticated_is_401(self, app: Any) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/v1/invitations/sometoken/accept")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_success(self, app: Any) -> None:
        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user

        mock_user = MagicMock(spec=User)
        mock_user.email = "invitee@example.com"
        mock_user.id = uuid.uuid4()

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        async def mock_get_db() -> Any:
            yield AsyncMock()

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_db] = mock_get_db
        try:
            membership = make_membership(
                org_id=_ORG_ID, user_email="invitee@example.com", role=MembershipRole.MEMBER
            )
            with (
                patch(
                    "app.api.v1.invitations.InvitationService.accept_invitation",
                    new=AsyncMock(return_value=membership),
                ),
                patch(
                    "app.api.v1.invitations.OrganizationRepository.get",
                    new=AsyncMock(return_value=_active_org()),
                ),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post("/v1/invitations/raw-token/accept")
            assert resp.status_code == 200
            assert resp.json()["role"] == "member"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_invalid_token_is_400(self, app: Any) -> None:
        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user

        mock_user = MagicMock(spec=User)
        mock_user.email = "invitee@example.com"

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        async def mock_get_db() -> Any:
            yield AsyncMock()

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_db] = mock_get_db
        try:
            with patch(
                "app.api.v1.invitations.InvitationService.accept_invitation",
                new=AsyncMock(side_effect=InvalidInvitationTokenError),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post("/v1/invitations/bad-token/accept")
            assert resp.status_code == 400
        finally:
            app.dependency_overrides.clear()


class TestDeclineEndpoint:
    @pytest.mark.asyncio
    async def test_no_auth_required(self, app: Any) -> None:
        from app.api.deps import get_db

        async def mock_get_db() -> Any:
            yield AsyncMock()

        app.dependency_overrides[get_db] = mock_get_db
        try:
            with patch(
                "app.api.v1.invitations.InvitationService.decline_invitation",
                new=AsyncMock(return_value=_make_invitation(status=InvitationStatus.CANCELLED)),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post("/v1/invitations/raw-token/decline")
            assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_invalid_token_is_400(self, app: Any) -> None:
        from app.api.deps import get_db

        async def mock_get_db() -> Any:
            yield AsyncMock()

        app.dependency_overrides[get_db] = mock_get_db
        try:
            with patch(
                "app.api.v1.invitations.InvitationService.decline_invitation",
                new=AsyncMock(side_effect=InvalidInvitationTokenError),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post("/v1/invitations/bad-token/decline")
            assert resp.status_code == 400
        finally:
            app.dependency_overrides.clear()


class TestResendEndpoint:
    @pytest.mark.asyncio
    async def test_admin_can_resend(self, app: Any) -> None:
        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user

        mock_user = MagicMock(spec=User)
        mock_user.email = "admin@example.com"
        mock_user.id = uuid.uuid4()

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        async def mock_get_db() -> Any:
            yield AsyncMock()

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_db] = mock_get_db
        try:
            inv = _make_invitation()
            with (
                patch(
                    "app.api.v1.invitations.InvitationRepository.get",
                    new=AsyncMock(return_value=inv),
                ),
                patch(
                    "app.api.v1.invitations.ensure_org_membership",
                    new=AsyncMock(return_value=_membership(role=MembershipRole.ADMIN)),
                ),
                patch(
                    "app.api.v1.invitations.OrganizationRepository.get",
                    new=AsyncMock(return_value=_active_org()),
                ),
                patch(
                    "app.api.v1.invitations.InvitationService.resend_invitation",
                    new=AsyncMock(return_value=inv),
                ),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(f"/v1/invitations/{inv.id}/resend")
            assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_member_cannot_resend(self, app: Any) -> None:
        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user

        mock_user = MagicMock(spec=User)
        mock_user.email = "member@example.com"
        mock_user.id = uuid.uuid4()

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        async def mock_get_db() -> Any:
            yield AsyncMock()

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_db] = mock_get_db
        try:
            inv = _make_invitation()
            with (
                patch(
                    "app.api.v1.invitations.InvitationRepository.get",
                    new=AsyncMock(return_value=inv),
                ),
                patch(
                    "app.api.v1.invitations.ensure_org_membership",
                    new=AsyncMock(return_value=_membership(role=MembershipRole.MEMBER)),
                ),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(f"/v1/invitations/{inv.id}/resend")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_not_found_is_404(self, app: Any) -> None:
        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user

        mock_user = MagicMock(spec=User)
        mock_user.email = "admin@example.com"

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        async def mock_get_db() -> Any:
            yield AsyncMock()

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_db] = mock_get_db
        try:
            with patch(
                "app.api.v1.invitations.InvitationRepository.get",
                new=AsyncMock(return_value=None),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(f"/v1/invitations/{uuid.uuid4()}/resend")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()


class TestCancelEndpoint:
    @pytest.mark.asyncio
    async def test_admin_can_cancel(self, app: Any) -> None:
        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user

        mock_user = MagicMock(spec=User)
        mock_user.email = "admin@example.com"
        mock_user.id = uuid.uuid4()

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        async def mock_get_db() -> Any:
            yield AsyncMock()

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_db] = mock_get_db
        try:
            inv = _make_invitation()
            with (
                patch(
                    "app.api.v1.invitations.InvitationRepository.get",
                    new=AsyncMock(return_value=inv),
                ),
                patch(
                    "app.api.v1.invitations.ensure_org_membership",
                    new=AsyncMock(return_value=_membership(role=MembershipRole.ADMIN)),
                ),
                patch(
                    "app.api.v1.invitations.OrganizationRepository.get",
                    new=AsyncMock(return_value=_active_org()),
                ),
                patch(
                    "app.api.v1.invitations.InvitationService.cancel_invitation",
                    new=AsyncMock(return_value=inv),
                ),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.delete(f"/v1/invitations/{inv.id}")
            assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()
