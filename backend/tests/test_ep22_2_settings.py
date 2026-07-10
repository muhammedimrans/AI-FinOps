"""Tests for EP-22.2 — Settings Backend Integration.

Covers:
  - AuthService.update_profile / update_preferences / change_password / delete_account
  - PATCH /v1/auth/me, PATCH /v1/auth/me/preferences
  - POST /v1/auth/change-password
  - DELETE /v1/auth/me
  - PATCH /v1/organizations/{org_id} (description), DELETE /v1/organizations/{org_id}
  - PATCH /v1/organizations/{org_id}/api-keys/{key_id}

All tests are hermetic — no network calls, no real database.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.exceptions import (
    InvalidCredentialsError,
    OwnerOfSharedWorkspaceError,
    UsernameAlreadyTakenError,
)
from app.auth.password import hash_password
from app.auth.service import AuthService
from app.config.settings import Settings
from app.models.membership import Membership, MembershipRole
from app.models.organization import Organization
from app.models.user import User
from tests.conftest import make_api_key, make_membership, make_org, make_user

_ORG_ID = uuid.uuid4()


def _test_settings() -> Settings:
    return Settings(
        app_env="testing",
        app_secret_key="test-secret-key-with-at-least-32-chars!!",
        jwt_secret="test-jwt-secret-for-unit-tests-only!!",
    )


def _override_current_user(app: Any, user: User) -> None:
    from app.api.deps import get_db
    from app.auth.dependencies import get_current_user

    async def mock_get_user() -> User:
        return user

    async def mock_get_db() -> Any:
        yield AsyncMock()

    app.dependency_overrides[get_current_user] = mock_get_user
    app.dependency_overrides[get_db] = mock_get_db


# ══════════════════════════════════════════════════════════════════════════════
# AuthService — profile / preferences (service layer)
# ══════════════════════════════════════════════════════════════════════════════


class TestUpdateProfile:
    def setup_method(self) -> None:
        self.settings = _test_settings()
        self.svc = AuthService(AsyncMock(), self.settings)
        self.svc._user_repo = AsyncMock()

    @pytest.mark.asyncio
    async def test_updates_only_fields_present(self) -> None:
        user = make_user(display_name="Old Name", bio="old bio")
        updated = await self.svc.update_profile(
            user=user,
            display_name="New Name",
            set_fields={"display_name"},
        )
        assert updated.display_name == "New Name"
        assert updated.bio == "old bio"  # untouched — not in set_fields

    @pytest.mark.asyncio
    async def test_omitted_field_is_not_cleared(self) -> None:
        user = make_user(bio="keep me")
        await self.svc.update_profile(user=user, display_name="X", set_fields={"display_name"})
        assert user.bio == "keep me"

    @pytest.mark.asyncio
    async def test_explicit_null_clears_field(self) -> None:
        user = make_user(bio="clear me")
        await self.svc.update_profile(user=user, bio=None, set_fields={"bio"})
        assert user.bio is None

    @pytest.mark.asyncio
    async def test_rejects_taken_username(self) -> None:
        self.svc._user_repo.username_exists = AsyncMock(return_value=True)
        user = make_user(username="alice")
        with pytest.raises(UsernameAlreadyTakenError):
            await self.svc.update_profile(user=user, username="bob", set_fields={"username"})

    @pytest.mark.asyncio
    async def test_allows_keeping_own_username(self) -> None:
        self.svc._user_repo.username_exists = AsyncMock(return_value=False)
        user = make_user(username="alice")
        updated = await self.svc.update_profile(
            user=user, username="alice", set_fields={"username"}
        )
        assert updated.username == "alice"


class TestUpdatePreferences:
    @pytest.mark.asyncio
    async def test_shallow_merges_new_keys(self) -> None:
        svc = AuthService(AsyncMock(), _test_settings())
        user = make_user(preferences={"theme": "dark"})
        updated = await svc.update_preferences(user=user, patch={"currency": "EUR"})
        assert updated.preferences == {"theme": "dark", "currency": "EUR"}

    @pytest.mark.asyncio
    async def test_overwrites_existing_key(self) -> None:
        svc = AuthService(AsyncMock(), _test_settings())
        user = make_user(preferences={"theme": "dark"})
        updated = await svc.update_preferences(user=user, patch={"theme": "light"})
        assert updated.preferences == {"theme": "light"}


# ══════════════════════════════════════════════════════════════════════════════
# AuthService — change_password / delete_account (service layer)
# ══════════════════════════════════════════════════════════════════════════════


class TestChangePassword:
    def setup_method(self) -> None:
        self.settings = _test_settings()
        self.session_id = uuid.uuid4()
        self.svc = AuthService(AsyncMock(), self.settings)
        self.svc._session_repo = AsyncMock()

    @pytest.mark.asyncio
    async def test_wrong_current_password_raises(self) -> None:
        user = make_user(password_hash=hash_password("correct-horse"))
        with pytest.raises(InvalidCredentialsError):
            await self.svc.change_password(
                user=user,
                current_password="wrong",
                new_password="new-password-123",
                current_session_id=self.session_id,
            )

    @pytest.mark.asyncio
    async def test_success_rehashes_and_revokes_other_sessions(self) -> None:
        old_hash = hash_password("correct-horse")
        user = make_user(password_hash=old_hash)
        await self.svc.change_password(
            user=user,
            current_password="correct-horse",
            new_password="brand-new-password",
            current_session_id=self.session_id,
        )
        assert user.password_hash != old_hash
        self.svc._session_repo.revoke_all_for_user_except.assert_awaited_once_with(
            user.id, self.session_id
        )

    @pytest.mark.asyncio
    async def test_user_with_no_password_hash_raises(self) -> None:
        user = make_user(password_hash=None)
        with pytest.raises(InvalidCredentialsError):
            await self.svc.change_password(
                user=user,
                current_password="anything",
                new_password="brand-new-password",
                current_session_id=self.session_id,
            )


class TestDeleteAccount:
    def setup_method(self) -> None:
        self.settings = _test_settings()
        self.svc = AuthService(AsyncMock(), self.settings)
        self.svc._membership_repo = AsyncMock()
        self.svc._org_repo = AsyncMock()
        self.svc._user_repo = AsyncMock()
        self.svc._session_repo = AsyncMock()

    @pytest.mark.asyncio
    async def test_wrong_password_raises(self) -> None:
        user = make_user(password_hash=hash_password("correct-horse"))
        with pytest.raises(InvalidCredentialsError):
            await self.svc.delete_account(user=user, password="wrong")

    @pytest.mark.asyncio
    async def test_sole_owner_of_shared_workspace_is_blocked(self) -> None:
        user = make_user(email="owner@example.com", password_hash=hash_password("pw"))
        shared_org = make_org(name="Shared Co")
        m = make_membership(org_id=shared_org.id, user_email=user.email, role=MembershipRole.OWNER)
        m.organization = shared_org
        other_member = make_membership(org_id=shared_org.id, user_email="teammate@example.com")
        self.svc._membership_repo.list_by_user_email_with_orgs = AsyncMock(return_value=[m])
        self.svc._membership_repo.list_by_org_with_users = AsyncMock(return_value=[m, other_member])
        with pytest.raises(OwnerOfSharedWorkspaceError) as exc_info:
            await self.svc.delete_account(user=user, password="pw")
        assert exc_info.value.organization_name == "Shared Co"
        self.svc._user_repo.soft_delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_solo_owner_deletes_org_and_account(self) -> None:
        user = make_user(email="solo@example.com", password_hash=hash_password("pw"))
        personal_org = make_org(name="Solo's Workspace", is_personal=True)
        m = make_membership(
            org_id=personal_org.id, user_email=user.email, role=MembershipRole.OWNER
        )
        m.organization = personal_org
        self.svc._membership_repo.list_by_user_email_with_orgs = AsyncMock(return_value=[m])
        self.svc._membership_repo.list_by_org_with_users = AsyncMock(return_value=[m])
        self.svc._org_repo.get = AsyncMock(return_value=personal_org)

        # EP-25.1: delete_account() now cascade-soft-deletes every
        # dependent resource for each solely-owned org via fresh
        # repository instances — patch those out for this unit test
        # (the cascade itself is covered by test_ep25_1_personal_business.py).
        with (
            patch(
                "app.auth.service.ProjectRepository",
                return_value=MagicMock(
                    list_by_org=AsyncMock(return_value=MagicMock(items=[])), soft_delete=AsyncMock()
                ),
            ),
            patch(
                "app.auth.service.ProviderConnectionRepository",
                return_value=MagicMock(
                    list_by_org=AsyncMock(return_value=MagicMock(items=[])), soft_delete=AsyncMock()
                ),
            ),
            patch(
                "app.auth.service.BudgetRepository",
                return_value=MagicMock(
                    list_for_org=AsyncMock(return_value=[]), soft_delete=AsyncMock()
                ),
            ),
            patch(
                "app.auth.service.OrganizationApiKeyRepository",
                return_value=MagicMock(list=AsyncMock(return_value=[]), soft_delete=AsyncMock()),
            ),
            patch(
                "app.auth.service.InvitationRepository",
                return_value=MagicMock(list_pending_by_org=AsyncMock(return_value=[])),
            ),
        ):
            await self.svc.delete_account(user=user, password="pw")

        self.svc._org_repo.soft_delete.assert_awaited_once_with(personal_org, deleted_by=user.id)
        self.svc._user_repo.soft_delete.assert_awaited_once_with(user, deleted_by=user.id)
        self.svc._session_repo.revoke_all_for_user.assert_awaited_once_with(user.id)

    @pytest.mark.asyncio
    async def test_non_owner_membership_is_left_alone(self) -> None:
        user = make_user(email="member@example.com", password_hash=hash_password("pw"))
        other_org = make_org(name="Someone Else's Org")
        m = make_membership(org_id=other_org.id, user_email=user.email, role=MembershipRole.MEMBER)
        m.organization = other_org
        self.svc._membership_repo.list_by_user_email_with_orgs = AsyncMock(return_value=[m])

        await self.svc.delete_account(user=user, password="pw")

        self.svc._org_repo.soft_delete.assert_not_awaited()
        self.svc._user_repo.soft_delete.assert_awaited_once()


# ══════════════════════════════════════════════════════════════════════════════
# HTTP — PATCH /v1/auth/me, PATCH /v1/auth/me/preferences
# ══════════════════════════════════════════════════════════════════════════════


class TestUpdateProfileEndpoint:
    @pytest.mark.asyncio
    async def test_updates_display_name(self, app: Any) -> None:
        user = make_user(display_name="Old")
        _override_current_user(app, user)
        try:
            with patch(
                "app.api.v1.auth.AuthService.update_profile",
                new=AsyncMock(side_effect=lambda **kw: kw["user"]),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.patch("/v1/auth/me", json={"display_name": "New"})
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_taken_username_is_409(self, app: Any) -> None:
        user = make_user()
        _override_current_user(app, user)
        try:
            with patch(
                "app.api.v1.auth.AuthService.update_profile",
                new=AsyncMock(side_effect=UsernameAlreadyTakenError()),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.patch("/v1/auth/me", json={"username": "taken"})
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_unauthenticated_is_401(self, client: Any) -> None:
        resp = await client.patch("/v1/auth/me", json={"display_name": "X"})
        assert resp.status_code == 401


class TestUpdatePreferencesEndpoint:
    @pytest.mark.asyncio
    async def test_merges_preferences(self, app: Any) -> None:
        user = make_user(preferences={"theme": "dark"})
        _override_current_user(app, user)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.patch(
                    "/v1/auth/me/preferences", json={"preferences": {"currency": "EUR"}}
                )
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 200
        assert resp.json()["preferences"] == {"theme": "dark", "currency": "EUR"}

    @pytest.mark.asyncio
    async def test_unauthenticated_is_401(self, client: Any) -> None:
        resp = await client.patch("/v1/auth/me/preferences", json={"preferences": {}})
        assert resp.status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# HTTP — POST /v1/auth/change-password
# ══════════════════════════════════════════════════════════════════════════════


class TestChangePasswordEndpoint:
    @pytest.mark.asyncio
    async def test_success(self, app: Any) -> None:
        user = make_user(password_hash=hash_password("correct-horse"))
        _override_current_user(app, user)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.post(
                    "/v1/auth/change-password",
                    json={"current_password": "correct-horse", "new_password": "new-password-99"},
                )
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 200
        assert resp.json()["message"]

    @pytest.mark.asyncio
    async def test_wrong_current_password_is_401(self, app: Any) -> None:
        user = make_user(password_hash=hash_password("correct-horse"))
        _override_current_user(app, user)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.post(
                    "/v1/auth/change-password",
                    json={"current_password": "wrong", "new_password": "new-password-99"},
                )
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_short_new_password_is_422(self, app: Any) -> None:
        user = make_user(password_hash=hash_password("correct-horse"))
        _override_current_user(app, user)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.post(
                    "/v1/auth/change-password",
                    json={"current_password": "correct-horse", "new_password": "short"},
                )
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_unauthenticated_is_401(self, client: Any) -> None:
        resp = await client.post(
            "/v1/auth/change-password",
            json={"current_password": "a", "new_password": "brand-new-password"},
        )
        assert resp.status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# HTTP — DELETE /v1/auth/me
# ══════════════════════════════════════════════════════════════════════════════


class TestDeleteAccountEndpoint:
    @pytest.mark.asyncio
    async def test_success_returns_204(self, app: Any) -> None:
        user = make_user()
        _override_current_user(app, user)
        try:
            with patch(
                "app.api.v1.auth.AuthService.delete_account",
                new=AsyncMock(return_value=None),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.request(
                        "DELETE", "/v1/auth/me", json={"password": "correct-horse"}
                    )
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_wrong_password_is_401(self, app: Any) -> None:
        user = make_user()
        _override_current_user(app, user)
        try:
            with patch(
                "app.api.v1.auth.AuthService.delete_account",
                new=AsyncMock(side_effect=InvalidCredentialsError()),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.request("DELETE", "/v1/auth/me", json={"password": "wrong"})
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_sole_owner_of_shared_workspace_is_409(self, app: Any) -> None:
        user = make_user()
        _override_current_user(app, user)
        try:
            with patch(
                "app.api.v1.auth.AuthService.delete_account",
                new=AsyncMock(side_effect=OwnerOfSharedWorkspaceError("Shared Co")),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.request("DELETE", "/v1/auth/me", json={"password": "pw"})
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 409
        assert "Shared Co" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_unauthenticated_is_401(self, client: Any) -> None:
        resp = await client.request("DELETE", "/v1/auth/me", json={"password": "x"})
        assert resp.status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# HTTP — PATCH / DELETE /v1/organizations/{org_id}
# ══════════════════════════════════════════════════════════════════════════════


def _override_org_auth(app: Any, *, caller_role: MembershipRole, org: Organization) -> Any:
    from app.api.deps import get_db
    from app.auth.dependencies import get_current_user

    mock_user = MagicMock(spec=User)
    mock_user.email = "caller@example.com"
    mock_user.status = "active"

    async def mock_get_user() -> User:
        return mock_user  # type: ignore[return-value]

    async def mock_get_db() -> Any:
        yield AsyncMock()

    app.dependency_overrides[get_current_user] = mock_get_user
    app.dependency_overrides[get_db] = mock_get_db

    caller_membership = MagicMock(spec=Membership)
    caller_membership.role = caller_role

    org_repo = MagicMock()
    org_repo.get = AsyncMock(return_value=org)
    mem_repo_lookup = MagicMock()
    mem_repo_lookup.get_by_org_and_email = AsyncMock(return_value=caller_membership)
    return org_repo, mem_repo_lookup


def _auth_patches(org_repo: Any, mem_repo_lookup: Any) -> Any:
    return patch.multiple(
        "app.auth.dependencies",
        OrganizationRepository=MagicMock(return_value=org_repo),
        MembershipRepository=MagicMock(return_value=mem_repo_lookup),
    )


class TestUpdateOrganizationDescription:
    @pytest.mark.asyncio
    async def test_owner_can_update_description_only(self, app: Any) -> None:
        org = make_org(name="Acme", slug="acme")
        org.id = _ORG_ID
        org_repo, mem_repo_lookup = _override_org_auth(
            app, caller_role=MembershipRole.OWNER, org=org
        )
        try:
            updated = make_org(name="Acme", slug="acme", description="We build things.")
            updated.id = _ORG_ID
            with (
                _auth_patches(org_repo, mem_repo_lookup),
                patch(
                    "app.api.v1.organizations.OrganizationRepository.get",
                    new=AsyncMock(return_value=org),
                ),
                patch(
                    "app.api.v1.organizations.OrganizationRepository.update",
                    new=AsyncMock(return_value=updated),
                ) as mock_update,
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.patch(
                        f"/v1/organizations/{_ORG_ID}",
                        json={"description": "We build things."},
                    )
            assert resp.status_code == 200
            assert resp.json()["description"] == "We build things."
            mock_update.assert_awaited_once_with(org, description="We build things.")
        finally:
            app.dependency_overrides.clear()


class TestDeleteOrganizationEndpoint:
    @pytest.mark.asyncio
    async def test_owner_can_delete_non_personal_workspace(self, app: Any) -> None:
        org = make_org(name="Team Co", slug="team-co", is_personal=False)
        org.id = _ORG_ID
        org_repo, mem_repo_lookup = _override_org_auth(
            app, caller_role=MembershipRole.OWNER, org=org
        )
        try:
            with (
                _auth_patches(org_repo, mem_repo_lookup),
                patch(
                    "app.api.v1.organizations.OrganizationRepository.get",
                    new=AsyncMock(return_value=org),
                ),
                patch(
                    "app.api.v1.organizations.OrganizationRepository.soft_delete",
                    new=AsyncMock(return_value=org),
                ) as mock_delete,
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.delete(f"/v1/organizations/{_ORG_ID}")
            assert resp.status_code == 204
            mock_delete.assert_awaited_once()
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_admin_cannot_delete(self, app: Any) -> None:
        org = make_org(name="Team Co", slug="team-co", is_personal=False)
        org.id = _ORG_ID
        org_repo, mem_repo_lookup = _override_org_auth(
            app, caller_role=MembershipRole.ADMIN, org=org
        )
        try:
            with _auth_patches(org_repo, mem_repo_lookup):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.delete(f"/v1/organizations/{_ORG_ID}")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_personal_workspace_cannot_be_deleted(self, app: Any) -> None:
        org = make_org(name="Solo's Workspace", slug="solo", is_personal=True)
        org.id = _ORG_ID
        org_repo, mem_repo_lookup = _override_org_auth(
            app, caller_role=MembershipRole.OWNER, org=org
        )
        try:
            with (
                _auth_patches(org_repo, mem_repo_lookup),
                patch(
                    "app.api.v1.organizations.OrganizationRepository.get",
                    new=AsyncMock(return_value=org),
                ),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.delete(f"/v1/organizations/{_ORG_ID}")
            assert resp.status_code == 400
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_unauthenticated_is_401(self, app: Any) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.delete(f"/v1/organizations/{_ORG_ID}")
        assert resp.status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# HTTP — PATCH /v1/organizations/{org_id}/api-keys/{key_id}
# ══════════════════════════════════════════════════════════════════════════════


class TestUpdateApiKeyEndpoint:
    @pytest.mark.asyncio
    async def test_admin_can_rename(self, app: Any) -> None:
        org = make_org(name="Acme", slug="acme")
        org.id = _ORG_ID
        org_repo, mem_repo_lookup = _override_org_auth(
            app, caller_role=MembershipRole.ADMIN, org=org
        )
        key = make_api_key(org_id=_ORG_ID, name="Old name")
        renamed = make_api_key(org_id=_ORG_ID, name="New name")
        renamed.id = key.id
        try:
            with (
                _auth_patches(org_repo, mem_repo_lookup),
                patch(
                    "app.repositories.organization_api_key_repository."
                    "OrganizationApiKeyRepository.get",
                    new=AsyncMock(return_value=key),
                ),
                patch(
                    "app.repositories.organization_api_key_repository."
                    "OrganizationApiKeyRepository.update",
                    new=AsyncMock(return_value=renamed),
                ) as mock_update,
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.patch(
                        f"/v1/organizations/{_ORG_ID}/api-keys/{key.id}",
                        json={"name": "New name"},
                    )
            assert resp.status_code == 200
            assert resp.json()["name"] == "New name"
            mock_update.assert_awaited_once_with(key, name="New name")
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_member_cannot_rename(self, app: Any) -> None:
        org = make_org(name="Acme", slug="acme")
        org.id = _ORG_ID
        org_repo, mem_repo_lookup = _override_org_auth(
            app, caller_role=MembershipRole.MEMBER, org=org
        )
        try:
            with _auth_patches(org_repo, mem_repo_lookup):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.patch(
                        f"/v1/organizations/{_ORG_ID}/api-keys/{uuid.uuid4()}",
                        json={"name": "New name"},
                    )
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_key_from_another_org_is_404(self, app: Any) -> None:
        org = make_org(name="Acme", slug="acme")
        org.id = _ORG_ID
        org_repo, mem_repo_lookup = _override_org_auth(
            app, caller_role=MembershipRole.ADMIN, org=org
        )
        other_org_key = make_api_key(org_id=uuid.uuid4())
        try:
            with (
                _auth_patches(org_repo, mem_repo_lookup),
                patch(
                    "app.repositories.organization_api_key_repository."
                    "OrganizationApiKeyRepository.get",
                    new=AsyncMock(return_value=other_org_key),
                ),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.patch(
                        f"/v1/organizations/{_ORG_ID}/api-keys/{other_org_key.id}",
                        json={"name": "New name"},
                    )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_unauthenticated_is_401(self, app: Any) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.patch(
                f"/v1/organizations/{_ORG_ID}/api-keys/{uuid.uuid4()}",
                json={"name": "x"},
            )
        assert resp.status_code == 401
