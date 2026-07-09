"""Tests for EP-21.3 — First-Time User Onboarding.

Covers:
  - AuthService.complete_onboarding (service layer)
  - POST /v1/auth/onboarding/complete (HTTP layer)
  - GET /v1/auth/me and POST /v1/auth/register reflecting onboarding_completed
  - PATCH /v1/organizations/{org_id} (workspace rename, onboarding Step 2)

All tests are hermetic — no network calls, no real database.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config.settings import Settings
from app.models.membership import Membership, MembershipRole
from app.models.organization import Organization, OrganizationStatus
from app.models.user import User
from tests.conftest import make_org, make_user

_ORG_ID = uuid.uuid4()


def _test_settings() -> Settings:
    return Settings(
        app_env="testing",
        app_secret_key="test-secret-key-with-at-least-32-chars!!",
        jwt_secret="test-jwt-secret-for-unit-tests-only!!",
    )


# ══════════════════════════════════════════════════════════════════════════════
# AuthService.complete_onboarding (service layer)
# ══════════════════════════════════════════════════════════════════════════════


class TestAuthServiceCompleteOnboarding:
    def setup_method(self) -> None:
        self.settings = _test_settings()
        self.mock_session = AsyncMock()
        self.user = make_user(email="new@example.com")

    def _make_svc(self) -> Any:
        from app.auth.service import AuthService

        svc = AuthService(self.mock_session, self.settings)
        svc._user_repo = AsyncMock()
        svc._session_repo = AsyncMock()
        svc._verify_repo = AsyncMock()
        svc._reset_repo = AsyncMock()
        svc._membership_repo = AsyncMock()
        return svc

    @pytest.mark.asyncio
    async def test_sets_onboarding_completed_at(self) -> None:
        assert self.user.onboarding_completed_at is None
        svc = self._make_svc()

        updated = await svc.complete_onboarding(user=self.user)

        assert updated is self.user
        assert updated.onboarding_completed_at is not None

    @pytest.mark.asyncio
    async def test_idempotent_when_called_twice(self) -> None:
        svc = self._make_svc()

        first = await svc.complete_onboarding(user=self.user)
        first_ts = first.onboarding_completed_at
        second = await svc.complete_onboarding(user=self.user)

        assert second.onboarding_completed_at is not None
        assert second.onboarding_completed_at >= first_ts


# ══════════════════════════════════════════════════════════════════════════════
# POST /v1/auth/onboarding/complete (HTTP layer)
# ══════════════════════════════════════════════════════════════════════════════


def _override_current_user(app: Any, user: User) -> None:
    from app.api.deps import get_db
    from app.auth.dependencies import get_current_user

    async def mock_get_user() -> User:
        return user

    async def mock_get_db() -> Any:
        yield AsyncMock()

    app.dependency_overrides[get_current_user] = mock_get_user
    app.dependency_overrides[get_db] = mock_get_db


class TestCompleteOnboardingEndpoint:
    @pytest.mark.asyncio
    async def test_marks_user_onboarded_and_returns_true(self, app: Any) -> None:
        user = make_user(email="fresh@example.com")
        assert user.onboarding_completed_at is None
        _override_current_user(app, user)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.post("/v1/auth/onboarding/complete")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        body = resp.json()
        assert body["onboarding_completed"] is True
        assert body["email"] == "fresh@example.com"

    @pytest.mark.asyncio
    async def test_unauthenticated_is_401(self, client: Any) -> None:
        resp = await client.post("/v1/auth/onboarding/complete")
        assert resp.status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# onboarding_completed surfaced on /me and /register
# ══════════════════════════════════════════════════════════════════════════════


class TestOnboardingCompletedOnMe:
    @pytest.mark.asyncio
    async def test_me_reflects_false_for_new_user(self, app: Any) -> None:
        user = make_user(email="me@example.com")
        _override_current_user(app, user)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get("/v1/auth/me")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        assert resp.json()["onboarding_completed"] is False

    @pytest.mark.asyncio
    async def test_me_reflects_true_once_completed(self, app: Any) -> None:
        from datetime import UTC, datetime

        user = make_user(email="me2@example.com")
        user.onboarding_completed_at = datetime.now(UTC)
        _override_current_user(app, user)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get("/v1/auth/me")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        assert resp.json()["onboarding_completed"] is True


class TestOnboardingCompletedOnRegister:
    @pytest.mark.asyncio
    async def test_register_response_has_onboarding_completed_false(self, client: Any) -> None:
        from app.auth.service import TokenPair

        user = make_user(email="newreg@example.com", display_name="New Reg")
        workspace = make_org(name="New Reg's Workspace", slug="new-reg-workspace")
        workspace.is_personal = True
        pair = TokenPair(access_token="a.b.c", refresh_token="r", expires_in=1800)

        with patch(
            "app.api.v1.auth.AuthService.register",
            new=AsyncMock(return_value=(pair, user, workspace)),
        ):
            resp = await client.post(
                "/v1/auth/register",
                json={
                    "email": "newreg@example.com",
                    "password": "correct-horse-battery-staple",
                    "display_name": "New Reg",
                },
            )

        assert resp.status_code == 201
        assert resp.json()["user"]["onboarding_completed"] is False


# ══════════════════════════════════════════════════════════════════════════════
# PATCH /v1/organizations/{org_id} (workspace rename)
# ══════════════════════════════════════════════════════════════════════════════


def _override_org_write_auth(app: Any, *, caller_role: MembershipRole) -> tuple[Any, Any]:
    """Override auth so the caller is a member of _ORG_ID with the given role,
    mirroring tests/test_member_management.py's _override_auth helper."""
    from app.api.deps import get_db
    from app.auth.dependencies import get_current_user

    mock_user = MagicMock(spec=User)
    mock_user.email = "caller@example.com"
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

    return org_repo, mem_repo_for_org_lookup


class TestUpdateOrganizationEndpoint:
    @pytest.mark.asyncio
    async def test_owner_can_rename_workspace(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_org_write_auth(app, caller_role=MembershipRole.OWNER)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                renamed = make_org(name="My New Workspace Name", slug="acme")
                renamed.id = _ORG_ID
                with (
                    patch(
                        "app.api.v1.organizations.OrganizationRepository.get",
                        new=AsyncMock(return_value=renamed),
                    ),
                    patch(
                        "app.api.v1.organizations.OrganizationRepository.update",
                        new=AsyncMock(return_value=renamed),
                    ),
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.patch(
                            f"/v1/organizations/{_ORG_ID}",
                            json={"name": "My New Workspace Name"},
                        )
            assert resp.status_code == 200
            body = resp.json()
            assert body["name"] == "My New Workspace Name"
            assert body["slug"] == "acme"
            assert body["role"] == "owner"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_member_cannot_rename_workspace(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_org_write_auth(app, caller_role=MembershipRole.MEMBER)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.patch(f"/v1/organizations/{_ORG_ID}", json={"name": "Nope"})
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_empty_name_is_422(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_org_write_auth(app, caller_role=MembershipRole.OWNER)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.patch(f"/v1/organizations/{_ORG_ID}", json={"name": ""})
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_unauthenticated_is_401(self, app: Any) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.patch(f"/v1/organizations/{_ORG_ID}", json={"name": "x"})
        assert resp.status_code == 401
