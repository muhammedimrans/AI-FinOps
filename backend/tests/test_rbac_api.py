"""Tests for RBAC introspection endpoints (EP-13).

Covers:
  GET /v1/rbac/roles       — role → permission mapping
  GET /v1/rbac/permissions — every defined permission

All tests are hermetic — no network calls, no real database.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.rbac import ROLE_PERMISSIONS, Permission
from app.models.membership import MembershipRole
from app.models.user import User


def _authenticated_client_kwargs(app: Any) -> None:
    from app.api.deps import get_db
    from app.auth.dependencies import get_current_user

    mock_user = MagicMock(spec=User)
    mock_user.email = "someone@example.com"

    async def mock_get_user() -> User:
        return mock_user  # type: ignore[return-value]

    async def mock_get_db() -> Any:
        yield AsyncMock()

    app.dependency_overrides[get_current_user] = mock_get_user
    app.dependency_overrides[get_db] = mock_get_db


class TestListRolesEndpoint:
    @pytest.mark.asyncio
    async def test_unauthenticated_is_401(self, app: Any) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/v1/rbac/roles")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_authenticated_returns_all_roles(self, app: Any) -> None:
        _authenticated_client_kwargs(app)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get("/v1/rbac/roles")
            assert resp.status_code == 200
            body = resp.json()
            role_values = {r["role"] for r in body["roles"]}
            assert role_values == {"owner", "admin", "member", "viewer"}
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_owner_has_every_permission(self, app: Any) -> None:
        _authenticated_client_kwargs(app)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get("/v1/rbac/roles")
            body = resp.json()
            owner = next(r for r in body["roles"] if r["role"] == "owner")
            assert set(owner["permissions"]) == {p.value for p in Permission}
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_viewer_has_fewer_permissions_than_owner(self, app: Any) -> None:
        _authenticated_client_kwargs(app)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get("/v1/rbac/roles")
            body = resp.json()
            viewer = next(r for r in body["roles"] if r["role"] == "viewer")
            owner = next(r for r in body["roles"] if r["role"] == "owner")
            assert len(viewer["permissions"]) < len(owner["permissions"])
            assert set(viewer["permissions"]).issubset(set(owner["permissions"]))
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_response_matches_rbac_module_exactly(self, app: Any) -> None:
        """The API must never drift from the enforcement mapping in app/auth/rbac.py."""
        _authenticated_client_kwargs(app)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get("/v1/rbac/roles")
            body = resp.json()
            for row in body["roles"]:
                role = MembershipRole(row["role"])
                expected = {p.value for p in ROLE_PERMISSIONS[role]}
                assert set(row["permissions"]) == expected
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_roles_have_human_readable_labels(self, app: Any) -> None:
        _authenticated_client_kwargs(app)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get("/v1/rbac/roles")
            body = resp.json()
            labels = {r["role"]: r["label"] for r in body["roles"]}
            assert labels["owner"] == "Owner"
            assert labels["viewer"] == "Viewer"
        finally:
            app.dependency_overrides.clear()


class TestListPermissionsEndpoint:
    @pytest.mark.asyncio
    async def test_unauthenticated_is_401(self, app: Any) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/v1/rbac/permissions")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_returns_every_permission(self, app: Any) -> None:
        _authenticated_client_kwargs(app)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get("/v1/rbac/permissions")
            body = resp.json()
            values = {p["permission"] for p in body["permissions"]}
            assert values == {p.value for p in Permission}
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_permission_split_into_domain_and_action(self, app: Any) -> None:
        _authenticated_client_kwargs(app)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get("/v1/rbac/permissions")
            body = resp.json()
            org_read = next(p for p in body["permissions"] if p["permission"] == "org:read")
            assert org_read["domain"] == "org"
            assert org_read["action"] == "read"
        finally:
            app.dependency_overrides.clear()
