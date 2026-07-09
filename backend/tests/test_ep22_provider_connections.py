"""Tests for Provider Connections CRUD API (EP-22).

Covers:
  - GET/POST/PATCH/DELETE /v1/organizations/{org_id}/provider-connections[...]
  - POST .../provider-connections/{id}/test
  - PROVIDER_READ (every role) / PROVIDER_WRITE / PROVIDER_DELETE
    (ADMIN+OWNER only — MEMBER has PROVIDER_READ but not WRITE/DELETE,
    per app.auth.rbac._MEMBER_PERMS vs _ADMIN_PERMS) authorization

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
from app.models.organization import Organization, OrganizationStatus
from app.models.provider_connection import ProviderConnection, ProviderHealthStatus, ProviderType
from app.models.user import User
from app.providers.errors import AuthenticationError
from tests.conftest import make_provider_connection

_ORG_ID = uuid.uuid4()


def _timestamped(conn: ProviderConnection) -> ProviderConnection:
    """make_provider_connection() returns a transient instance with no
    created_at/updated_at (only populated on a real flush/refresh) — set
    them explicitly so ProviderConnectionResponse serialization succeeds,
    matching tests/test_member_management.py's identical need."""
    conn.created_at = datetime.now(UTC)
    conn.updated_at = datetime.now(UTC)
    return conn


def _override_auth(app: Any, *, caller_role: MembershipRole) -> tuple[Any, Any]:
    """Mirrors tests/test_member_management.py's _override_auth helper."""
    from app.api.deps import get_db
    from app.auth.dependencies import get_current_user

    mock_user = MagicMock(spec=User)
    mock_user.email = "caller@example.com"
    mock_user.status = "active"

    async def mock_get_user() -> User:
        return mock_user

    async def mock_get_db() -> Any:
        yield AsyncMock()

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


class TestListProviderConnectionsEndpoint:
    @pytest.mark.asyncio
    async def test_unauthenticated_is_401(self, app: Any) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get(f"/v1/organizations/{_ORG_ID}/provider-connections")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_viewer_can_list(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.VIEWER)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                conn = _timestamped(
                    make_provider_connection(org_id=_ORG_ID, display_name="OpenAI prod")
                )
                with patch(
                    "app.api.v1.provider_connections.ProviderConnectionRepository.list_by_org",
                    new=AsyncMock(
                        return_value=type("Page", (), {"items": [conn], "next_cursor": None})()
                    ),
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.get(f"/v1/organizations/{_ORG_ID}/provider-connections")
            assert resp.status_code == 200
            body = resp.json()
            assert body["total"] == 1
            assert body["connections"][0]["display_name"] == "OpenAI prod"
            assert body["connections"][0]["health_status"] == "unknown"
        finally:
            app.dependency_overrides.clear()


class TestCreateProviderConnectionEndpoint:
    @pytest.mark.asyncio
    async def test_admin_can_create(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.ADMIN)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                created = _timestamped(
                    make_provider_connection(org_id=_ORG_ID, display_name="My OpenAI")
                )
                with patch(
                    "app.api.v1.provider_connections.ProviderConnectionRepository.create",
                    new=AsyncMock(return_value=created),
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.post(
                            f"/v1/organizations/{_ORG_ID}/provider-connections",
                            json={"provider_type": "openai", "display_name": "My OpenAI"},
                        )
            assert resp.status_code == 201
            assert resp.json()["display_name"] == "My OpenAI"
            assert resp.json()["is_active"] is True
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_invalid_provider_type_is_422(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.ADMIN)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(
                        f"/v1/organizations/{_ORG_ID}/provider-connections",
                        json={"provider_type": "not-a-provider", "display_name": "X"},
                    )
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_member_cannot_create(self, app: Any) -> None:
        """MEMBER has PROVIDER_READ but not PROVIDER_WRITE — only ADMIN/OWNER can."""
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.MEMBER)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(
                        f"/v1/organizations/{_ORG_ID}/provider-connections",
                        json={"provider_type": "openai", "display_name": "Nope"},
                    )
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()


class TestUpdateProviderConnectionEndpoint:
    @pytest.mark.asyncio
    async def test_update_display_name_and_active(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.ADMIN)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                existing = _timestamped(
                    make_provider_connection(org_id=_ORG_ID, display_name="Old")
                )
                updated = _timestamped(make_provider_connection(org_id=_ORG_ID, display_name="New"))
                updated.id = existing.id
                updated.is_active = False
                with (
                    patch(
                        "app.api.v1.provider_connections.ProviderConnectionRepository.get",
                        new=AsyncMock(return_value=existing),
                    ),
                    patch(
                        "app.api.v1.provider_connections.ProviderConnectionRepository.update",
                        new=AsyncMock(return_value=updated),
                    ),
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.patch(
                            f"/v1/organizations/{_ORG_ID}/provider-connections/{existing.id}",
                            json={"display_name": "New", "is_active": False},
                        )
            assert resp.status_code == 200
            assert resp.json()["display_name"] == "New"
            assert resp.json()["is_active"] is False
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_not_found_is_404(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.ADMIN)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                with patch(
                    "app.api.v1.provider_connections.ProviderConnectionRepository.get",
                    new=AsyncMock(return_value=None),
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.patch(
                            f"/v1/organizations/{_ORG_ID}/provider-connections/{uuid.uuid4()}",
                            json={"display_name": "X"},
                        )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()


class TestDeleteProviderConnectionEndpoint:
    @pytest.mark.asyncio
    async def test_admin_can_delete(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.ADMIN)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                existing = _timestamped(make_provider_connection(org_id=_ORG_ID))
                with (
                    patch(
                        "app.api.v1.provider_connections.ProviderConnectionRepository.get",
                        new=AsyncMock(return_value=existing),
                    ),
                    patch(
                        "app.api.v1.provider_connections.ProviderConnectionRepository.soft_delete",
                        new=AsyncMock(return_value=existing),
                    ) as soft_delete,
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.delete(
                            f"/v1/organizations/{_ORG_ID}/provider-connections/{existing.id}"
                        )
            assert resp.status_code == 204
            soft_delete.assert_awaited_once()
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_member_cannot_delete(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.MEMBER)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.delete(
                        f"/v1/organizations/{_ORG_ID}/provider-connections/{uuid.uuid4()}"
                    )
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()


class TestTestProviderConnectionEndpoint:
    @pytest.mark.asyncio
    async def test_successful_test_marks_healthy(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.ADMIN)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                existing = _timestamped(
                    make_provider_connection(org_id=_ORG_ID, provider_type=ProviderType.OPENAI)
                )
                adapter = AsyncMock()
                adapter.verify_auth = AsyncMock(return_value=None)
                with (
                    patch(
                        "app.api.v1.provider_connections.ProviderConnectionRepository.get",
                        new=AsyncMock(return_value=existing),
                    ),
                    patch(
                        "app.api.v1.provider_connections.ProviderConnectionRepository.update",
                        new=AsyncMock(return_value=existing),
                    ),
                    patch(
                        "app.api.v1.provider_connections._get_adapter",
                        return_value=adapter,
                    ),
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.post(
                            f"/v1/organizations/{_ORG_ID}/provider-connections/{existing.id}/test"
                        )
            assert resp.status_code == 200
            body = resp.json()
            assert body["tested"] is True
            assert body["health_status"] == "healthy"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_failed_test_marks_critical(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.ADMIN)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                existing = _timestamped(
                    make_provider_connection(org_id=_ORG_ID, provider_type=ProviderType.OPENAI)
                )
                adapter = AsyncMock()
                adapter.verify_auth = AsyncMock(side_effect=AuthenticationError("bad key"))
                with (
                    patch(
                        "app.api.v1.provider_connections.ProviderConnectionRepository.get",
                        new=AsyncMock(return_value=existing),
                    ),
                    patch(
                        "app.api.v1.provider_connections.ProviderConnectionRepository.update",
                        new=AsyncMock(return_value=existing),
                    ),
                    patch(
                        "app.api.v1.provider_connections._get_adapter",
                        return_value=adapter,
                    ),
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.post(
                            f"/v1/organizations/{_ORG_ID}/provider-connections/{existing.id}/test"
                        )
            assert resp.status_code == 200
            body = resp.json()
            assert body["tested"] is True
            assert body["health_status"] == "critical"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_unsupported_provider_returns_untested(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.ADMIN)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                existing = _timestamped(
                    make_provider_connection(org_id=_ORG_ID, provider_type=ProviderType.OLLAMA)
                )
                existing.health_status = ProviderHealthStatus.UNKNOWN
                with patch(
                    "app.api.v1.provider_connections.ProviderConnectionRepository.get",
                    new=AsyncMock(return_value=existing),
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.post(
                            f"/v1/organizations/{_ORG_ID}/provider-connections/{existing.id}/test"
                        )
            assert resp.status_code == 200
            body = resp.json()
            assert body["tested"] is False
        finally:
            app.dependency_overrides.clear()
