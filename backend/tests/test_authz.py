"""Multi-tenant authorization tests — org-membership enforcement.

Covers ensure_org_membership / get_query_org_membership (the OrgScopedMembership
dependency) and its wiring into the org-scoped read APIs:

  401 — missing/invalid JWT
  404 — organization does not exist (or is soft-deleted)
  403 — organization suspended/archived, or caller is not a member
  200 — member of an active organization
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.auth.dependencies import ensure_org_membership
from app.models.membership import Membership
from app.models.organization import Organization, OrganizationStatus
from app.models.user import User

_ORG_ID = uuid.uuid4()


def _user(email: str = "member@example.com") -> User:
    user = MagicMock(spec=User)
    user.email = email
    return user


def _org(status: OrganizationStatus = OrganizationStatus.ACTIVE) -> Organization:
    org = MagicMock(spec=Organization)
    org.id = _ORG_ID
    org.status = status
    return org


def _patch_repos(org: Organization | None, membership: Membership | None) -> Any:
    """Patch both repositories used by ensure_org_membership."""
    org_repo = MagicMock()
    org_repo.get = AsyncMock(return_value=org)
    mem_repo = MagicMock()
    mem_repo.get_by_org_and_email = AsyncMock(return_value=membership)
    return patch.multiple(
        "app.auth.dependencies",
        OrganizationRepository=MagicMock(return_value=org_repo),
        MembershipRepository=MagicMock(return_value=mem_repo),
    )


class TestEnsureOrgMembership:
    """Unit tests for the core guard."""

    @pytest.mark.asyncio
    async def test_unknown_org_returns_404(self) -> None:
        with _patch_repos(org=None, membership=None):
            with pytest.raises(HTTPException) as exc:
                await ensure_org_membership(AsyncMock(), user=_user(), org_id=_ORG_ID)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_suspended_org_returns_403(self) -> None:
        membership = MagicMock(spec=Membership)
        with _patch_repos(org=_org(OrganizationStatus.SUSPENDED), membership=membership):
            with pytest.raises(HTTPException) as exc:
                await ensure_org_membership(AsyncMock(), user=_user(), org_id=_ORG_ID)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_archived_org_returns_403(self) -> None:
        membership = MagicMock(spec=Membership)
        with _patch_repos(org=_org(OrganizationStatus.ARCHIVED), membership=membership):
            with pytest.raises(HTTPException) as exc:
                await ensure_org_membership(AsyncMock(), user=_user(), org_id=_ORG_ID)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_non_member_returns_403(self) -> None:
        with _patch_repos(org=_org(), membership=None):
            with pytest.raises(HTTPException) as exc:
                await ensure_org_membership(AsyncMock(), user=_user(), org_id=_ORG_ID)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_member_of_active_org_returns_membership(self) -> None:
        membership = MagicMock(spec=Membership)
        with _patch_repos(org=_org(), membership=membership):
            result = await ensure_org_membership(AsyncMock(), user=_user(), org_id=_ORG_ID)
        assert result is membership

    @pytest.mark.asyncio
    async def test_membership_lookup_uses_caller_email(self) -> None:
        """The membership check must be keyed to the authenticated user."""
        membership = MagicMock(spec=Membership)
        org_repo = MagicMock()
        org_repo.get = AsyncMock(return_value=_org())
        mem_repo = MagicMock()
        mem_repo.get_by_org_and_email = AsyncMock(return_value=membership)
        with patch.multiple(
            "app.auth.dependencies",
            OrganizationRepository=MagicMock(return_value=org_repo),
            MembershipRepository=MagicMock(return_value=mem_repo),
        ):
            await ensure_org_membership(
                AsyncMock(), user=_user("alice@corp.com"), org_id=_ORG_ID
            )
        mem_repo.get_by_org_and_email.assert_awaited_once_with(
            org_id=_ORG_ID, user_email="alice@corp.com"
        )


class TestDashboardOrgScoping:
    """API-level tests: the dashboard endpoints run the membership guard."""

    def _client(self, app: Any, org: Organization | None, membership: Membership | None) -> Any:
        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user

        async def mock_get_user() -> User:
            return _user()

        async def mock_get_db() -> Any:
            yield AsyncMock()

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_db] = mock_get_db
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    @pytest.mark.asyncio
    async def test_overview_unauthenticated_is_401(self, app: Any) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get(
                "/v1/dashboard/overview", params={"organization_id": str(_ORG_ID)}
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_overview_non_member_is_403(self, app: Any) -> None:
        try:
            async with self._client(app, org=_org(), membership=None) as ac:
                with _patch_repos(org=_org(), membership=None):
                    resp = await ac.get(
                        "/v1/dashboard/overview",
                        params={"organization_id": str(_ORG_ID)},
                    )
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_overview_unknown_org_is_404(self, app: Any) -> None:
        try:
            async with self._client(app, org=None, membership=None) as ac:
                with _patch_repos(org=None, membership=None):
                    resp = await ac.get(
                        "/v1/dashboard/overview",
                        params={"organization_id": str(_ORG_ID)},
                    )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_usage_collect_unauthenticated_is_401(self, app: Any) -> None:
        """Collection triggers hit live provider APIs — must never be anonymous."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/v1/usage/collect",
                json={
                    "organization_id": str(_ORG_ID),
                    "start_date": "2026-06-01T00:00:00Z",
                    "end_date": "2026-06-02T00:00:00Z",
                },
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_provider_test_connection_unauthenticated_is_401(self, app: Any) -> None:
        """Provider connectivity tests use server-side API keys — must never be anonymous."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/v1/providers/openai/test")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_provider_info_unauthenticated_is_401(self, app: Any) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/v1/providers/openai/info")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_usage_events_unauthenticated_is_401(self, app: Any) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get(
                "/v1/usage/events", params={"organization_id": str(_ORG_ID)}
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_pricing_models_non_member_is_403(self, app: Any) -> None:
        try:
            async with self._client(app, org=_org(), membership=None) as ac:
                with _patch_repos(org=_org(), membership=None):
                    resp = await ac.get(
                        "/v1/pricing/models",
                        params={"organization_id": str(_ORG_ID)},
                    )
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_analytics_non_member_is_403(self, app: Any) -> None:
        try:
            async with self._client(app, org=_org(), membership=None) as ac:
                with _patch_repos(org=_org(), membership=None):
                    resp = await ac.get(
                        "/v1/analytics/usage",
                        params={
                            "organization_id": str(_ORG_ID),
                            "start_date": "2026-06-01",
                            "end_date": "2026-06-30",
                        },
                    )
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()
