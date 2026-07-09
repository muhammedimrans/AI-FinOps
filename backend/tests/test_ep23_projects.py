"""Tests for Projects CRUD API (EP-23).

Covers:
  - GET/POST/PATCH/DELETE /v1/organizations/{org_id}/projects[...]
  - PROJECT_READ / PROJECT_WRITE / PROJECT_DELETE authorization

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
from app.models.project import Project
from app.models.user import User
from tests.conftest import make_project

_ORG_ID = uuid.uuid4()


def _timestamped(project: Project) -> Project:
    """make_project() returns a transient instance with no created_at/
    updated_at (those are only populated on a real flush/refresh) — set
    them explicitly so ProjectResponse serialization succeeds, matching
    tests/test_member_management.py's identical need for MemberResponse."""
    project.created_at = datetime.now(UTC)
    project.updated_at = datetime.now(UTC)
    return project


def _override_auth(app: Any, *, caller_role: MembershipRole) -> tuple[Any, Any]:
    """Override auth so the caller is a member of _ORG_ID with the given role,
    mirroring tests/test_member_management.py's _override_auth helper."""
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


class TestListProjectsEndpoint:
    @pytest.mark.asyncio
    async def test_unauthenticated_is_401(self, app: Any) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get(f"/v1/organizations/{_ORG_ID}/projects")
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
                p = _timestamped(make_project(org_id=_ORG_ID, name="Prod"))
                with patch(
                    "app.api.v1.projects.ProjectRepository.list_by_org",
                    new=AsyncMock(
                        return_value=type("Page", (), {"items": [p], "next_cursor": None})()
                    ),
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.get(f"/v1/organizations/{_ORG_ID}/projects")
            assert resp.status_code == 200
            body = resp.json()
            assert body["total"] == 1
            assert body["projects"][0]["name"] == "Prod"
        finally:
            app.dependency_overrides.clear()


class TestCreateProjectEndpoint:
    @pytest.mark.asyncio
    async def test_member_can_create(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.MEMBER)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                created = _timestamped(make_project(org_id=_ORG_ID, name="New Project"))
                with patch(
                    "app.api.v1.projects.ProjectRepository.create",
                    new=AsyncMock(return_value=created),
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.post(
                            f"/v1/organizations/{_ORG_ID}/projects",
                            json={"name": "New Project", "environment": "production"},
                        )
            assert resp.status_code == 201
            assert resp.json()["name"] == "New Project"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_viewer_cannot_create(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.VIEWER)
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
                        f"/v1/organizations/{_ORG_ID}/projects",
                        json={"name": "Nope"},
                    )
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_invalid_environment_is_422(self, app: Any) -> None:
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
                        f"/v1/organizations/{_ORG_ID}/projects",
                        json={"name": "X", "environment": "not-a-real-env"},
                    )
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_empty_name_is_422(self, app: Any) -> None:
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
                    resp = await ac.post(f"/v1/organizations/{_ORG_ID}/projects", json={"name": ""})
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.clear()


class TestUpdateProjectEndpoint:
    @pytest.mark.asyncio
    async def test_rename_project(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.MEMBER)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                existing = _timestamped(make_project(org_id=_ORG_ID, name="Old Name"))
                renamed = _timestamped(make_project(org_id=_ORG_ID, name="Renamed"))
                renamed.id = existing.id
                with (
                    patch(
                        "app.api.v1.projects.ProjectRepository.get",
                        new=AsyncMock(return_value=existing),
                    ),
                    patch(
                        "app.api.v1.projects.ProjectRepository.update",
                        new=AsyncMock(return_value=renamed),
                    ),
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.patch(
                            f"/v1/organizations/{_ORG_ID}/projects/{existing.id}",
                            json={"name": "Renamed"},
                        )
            assert resp.status_code == 200
            assert resp.json()["name"] == "Renamed"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_not_found_is_404(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.MEMBER)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                with patch(
                    "app.api.v1.projects.ProjectRepository.get",
                    new=AsyncMock(return_value=None),
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.patch(
                            f"/v1/organizations/{_ORG_ID}/projects/{uuid.uuid4()}",
                            json={"name": "X"},
                        )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()


class TestDeleteProjectEndpoint:
    @pytest.mark.asyncio
    async def test_admin_can_delete(self, app: Any) -> None:
        """MEMBER has PROJECT_WRITE but not PROJECT_DELETE — only ADMIN/OWNER can."""
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.ADMIN)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                existing = _timestamped(make_project(org_id=_ORG_ID))
                with (
                    patch(
                        "app.api.v1.projects.ProjectRepository.get",
                        new=AsyncMock(return_value=existing),
                    ),
                    patch(
                        "app.api.v1.projects.ProjectRepository.soft_delete",
                        new=AsyncMock(return_value=existing),
                    ) as soft_delete,
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.delete(
                            f"/v1/organizations/{_ORG_ID}/projects/{existing.id}"
                        )
            assert resp.status_code == 204
            soft_delete.assert_awaited_once()
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_viewer_cannot_delete(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.VIEWER)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.delete(f"/v1/organizations/{_ORG_ID}/projects/{uuid.uuid4()}")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()
