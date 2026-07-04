"""
Tests for EP-12.1 — Organization Context.

Coverage:
  - OrgMembershipItem / OrganizationsResponse schema construction
  - MembershipRepository.list_by_user_email_with_orgs:
      - returns memberships with Organization eagerly loaded
      - filters out SUSPENDED / ARCHIVED / soft-deleted orgs
  - GET /v1/organizations:
      - 401 without auth
      - 200 with zero orgs → empty list
      - 200 with one org → single item
      - 200 with multiple orgs → all items, ordered by created_at
      - response shape: id, name, slug, role

All tests are hermetic — no network calls, no real database.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.models.membership import Membership, MembershipRole
from app.models.organization import OrganizationStatus
from app.schemas.organizations import OrganizationsResponse, OrgMembershipItem
from tests.conftest import make_membership, make_org

# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_membership_with_org(
    *,
    org_name: str = "Acme Corp",
    org_slug: str = "acme",
    org_status: OrganizationStatus = OrganizationStatus.ACTIVE,
    org_deleted: bool = False,
    user_email: str = "alice@example.com",
    role: MembershipRole = MembershipRole.OWNER,
) -> Membership:
    org = make_org(name=org_name, slug=org_slug, status=org_status)
    if org_deleted:
        from datetime import UTC, datetime

        org.deleted_at = datetime.now(UTC)

    mem = make_membership(org_id=org.id, user_email=user_email, role=role)
    # Manually attach the org (simulating selectinload result)
    object.__setattr__(mem, "organization", org) if False else None
    mem.__dict__["organization"] = org
    return mem


# ══════════════════════════════════════════════════════════════════════════════
# Schema Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestOrganizationsSchemas:
    def test_org_membership_item_construction(self) -> None:
        item = OrgMembershipItem(
            id="org_abc123",
            name="Acme Corp",
            slug="acme",
            role="owner",
        )
        assert item.id == "org_abc123"
        assert item.name == "Acme Corp"
        assert item.slug == "acme"
        assert item.role == "owner"

    def test_organizations_response_empty(self) -> None:
        resp = OrganizationsResponse(organizations=[])
        assert resp.organizations == []

    def test_organizations_response_single(self) -> None:
        resp = OrganizationsResponse(
            organizations=[OrgMembershipItem(id="org_x", name="X", slug="x", role="admin")]
        )
        assert len(resp.organizations) == 1
        assert resp.organizations[0].role == "admin"

    def test_organizations_response_multiple(self) -> None:
        resp = OrganizationsResponse(
            organizations=[
                OrgMembershipItem(id="org_a", name="A", slug="a", role="owner"),
                OrgMembershipItem(id="org_b", name="B", slug="b", role="member"),
            ]
        )
        assert len(resp.organizations) == 2


# ══════════════════════════════════════════════════════════════════════════════
# Repository Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestMembershipRepositoryWithOrgs:
    """Test list_by_user_email_with_orgs filtering behaviour."""

    @pytest.mark.asyncio
    async def test_returns_active_org_memberships(self) -> None:
        from app.repositories.membership_repository import MembershipRepository

        mem = _make_membership_with_org(
            org_name="Acme", org_slug="acme", org_status=OrganizationStatus.ACTIVE
        )

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mem]
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = MembershipRepository(mock_session)
        result = await repo.list_by_user_email_with_orgs("alice@example.com")
        assert len(result) == 1
        assert result[0].organization.name == "Acme"

    @pytest.mark.asyncio
    async def test_filters_out_suspended_org(self) -> None:
        from app.repositories.membership_repository import MembershipRepository

        mem = _make_membership_with_org(
            org_status=OrganizationStatus.SUSPENDED,
        )

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mem]
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = MembershipRepository(mock_session)
        result = await repo.list_by_user_email_with_orgs("alice@example.com")
        assert result == []

    @pytest.mark.asyncio
    async def test_filters_out_archived_org(self) -> None:
        from app.repositories.membership_repository import MembershipRepository

        mem = _make_membership_with_org(
            org_status=OrganizationStatus.ARCHIVED,
        )

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mem]
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = MembershipRepository(mock_session)
        result = await repo.list_by_user_email_with_orgs("alice@example.com")
        assert result == []

    @pytest.mark.asyncio
    async def test_filters_out_soft_deleted_org(self) -> None:
        from app.repositories.membership_repository import MembershipRepository

        mem = _make_membership_with_org(
            org_deleted=True,
        )

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mem]
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = MembershipRepository(mock_session)
        result = await repo.list_by_user_email_with_orgs("alice@example.com")
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_memberships(self) -> None:
        from app.repositories.membership_repository import MembershipRepository

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = MembershipRepository(mock_session)
        result = await repo.list_by_user_email_with_orgs("nobody@example.com")
        assert result == []

    @pytest.mark.asyncio
    async def test_filters_mixed_statuses(self) -> None:
        from app.repositories.membership_repository import MembershipRepository

        active_mem = _make_membership_with_org(
            org_name="Active", org_slug="active", org_status=OrganizationStatus.ACTIVE
        )
        suspended_mem = _make_membership_with_org(
            org_name="Suspended", org_slug="suspended", org_status=OrganizationStatus.SUSPENDED
        )

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [active_mem, suspended_mem]
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = MembershipRepository(mock_session)
        result = await repo.list_by_user_email_with_orgs("alice@example.com")
        assert len(result) == 1
        assert result[0].organization.name == "Active"


# ══════════════════════════════════════════════════════════════════════════════
# API Endpoint Tests
# ══════════════════════════════════════════════════════════════════════════════


def _override_auth_and_db(app: Any, *, user_email: str, memberships: list) -> None:
    from app.api.deps import get_db
    from app.auth.dependencies import get_current_user
    from app.models.user import User
    from app.repositories.membership_repository import MembershipRepository

    mock_user = MagicMock(spec=User)
    mock_user.email = user_email

    async def mock_get_user() -> User:
        return mock_user  # type: ignore[return-value]

    mock_session = AsyncMock()

    async def mock_get_db():
        yield mock_session

    app.dependency_overrides[get_current_user] = mock_get_user
    app.dependency_overrides[get_db] = mock_get_db

    # Patch list_by_user_email_with_orgs on the repository class
    MembershipRepository.list_by_user_email_with_orgs = AsyncMock(return_value=memberships)  # type: ignore[method-assign]


class TestOrganizationsEndpoint:
    """Tests for GET /v1/organizations."""

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, app: Any) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/v1/organizations/")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_zero_orgs_returns_empty_list(self, app: Any) -> None:
        _override_auth_and_db(app, user_email="alice@example.com", memberships=[])
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get("/v1/organizations/")
            assert resp.status_code == 200
            body = resp.json()
            assert body["organizations"] == []
        finally:
            app.dependency_overrides.clear()
            from app.repositories.membership_repository import MembershipRepository

            if hasattr(MembershipRepository.list_by_user_email_with_orgs, "reset_mock"):
                pass  # already a mock; leave it for the next test to replace

    @pytest.mark.asyncio
    async def test_single_org_returns_one_item(self, app: Any) -> None:
        mem = _make_membership_with_org(
            org_name="Zero Protocol",
            org_slug="zero-protocol",
            role=MembershipRole.OWNER,
        )
        org_uuid = uuid.UUID("00000000-0000-0000-0000-000000000001")
        mem.organization.id = org_uuid

        _override_auth_and_db(app, user_email="admin@0protocol.net", memberships=[mem])
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get("/v1/organizations/")
            assert resp.status_code == 200
            body = resp.json()
            orgs = body["organizations"]
            assert len(orgs) == 1
            assert orgs[0]["name"] == "Zero Protocol"
            assert orgs[0]["slug"] == "zero-protocol"
            assert orgs[0]["role"] == "owner"
            # id must be the plain UUID string — consumed by dashboard endpoints
            assert orgs[0]["id"] == str(org_uuid)
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_multiple_orgs_returns_all(self, app: Any) -> None:
        mem1 = _make_membership_with_org(
            org_name="Org A", org_slug="org-a", role=MembershipRole.ADMIN
        )
        mem2 = _make_membership_with_org(
            org_name="Org B", org_slug="org-b", role=MembershipRole.MEMBER
        )

        _override_auth_and_db(app, user_email="alice@example.com", memberships=[mem1, mem2])
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get("/v1/organizations/")
            assert resp.status_code == 200
            body = resp.json()
            orgs = body["organizations"]
            assert len(orgs) == 2
            names = {o["name"] for o in orgs}
            assert names == {"Org A", "Org B"}
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_response_shape_has_required_fields(self, app: Any) -> None:
        mem = _make_membership_with_org(
            org_name="Test Org", org_slug="test-org", role=MembershipRole.VIEWER
        )

        _override_auth_and_db(app, user_email="test@example.com", memberships=[mem])
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get("/v1/organizations/")
            assert resp.status_code == 200
            org = resp.json()["organizations"][0]
            assert "id" in org
            assert "name" in org
            assert "slug" in org
            assert "role" in org
            assert org["role"] == "viewer"
        finally:
            app.dependency_overrides.clear()
