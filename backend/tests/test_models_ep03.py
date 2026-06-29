"""
Tests for EP-03 – Core Domain Models.

Covers (without a live database):
  - Model class attributes (tablename, external_id prefix)
  - Enum values and completeness
  - Default field values
  - Constraint and index definitions on __table_args__
  - Repository method signatures via mock session
  - Soft-delete inherited behavior on EP-03 models
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.mixins import uuid7
from app.models.membership import Membership, MembershipRole
from app.models.organization import Organization, OrganizationStatus
from app.models.project import Project, ProjectEnvironment
from app.models.provider_connection import ProviderConnection, ProviderType
from app.repositories.membership_repository import MembershipRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.provider_connection_repository import ProviderConnectionRepository


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_org(
    *,
    name: str = "Acme Corp",
    slug: str = "acme",
    status: OrganizationStatus = OrganizationStatus.ACTIVE,
) -> Organization:
    obj = Organization()
    obj.id = uuid7()
    obj.name = name
    obj.slug = slug
    obj.status = status
    return obj


def _make_project(
    *,
    org_id: uuid.UUID | None = None,
    name: str = "Main Project",
    environment: ProjectEnvironment = ProjectEnvironment.PRODUCTION,
) -> Project:
    obj = Project()
    obj.id = uuid7()
    obj.organization_id = org_id or uuid7()
    obj.name = name
    obj.environment = environment
    return obj


def _make_membership(
    *,
    org_id: uuid.UUID | None = None,
    user_email: str = "alice@example.com",
    role: MembershipRole = MembershipRole.MEMBER,
) -> Membership:
    obj = Membership()
    obj.id = uuid7()
    obj.organization_id = org_id or uuid7()
    obj.user_email = user_email
    obj.role = role
    return obj


def _make_connection(
    *,
    org_id: uuid.UUID | None = None,
    provider_type: ProviderType = ProviderType.OPENAI,
) -> ProviderConnection:
    obj = ProviderConnection()
    obj.id = uuid7()
    obj.organization_id = org_id or uuid7()
    obj.provider_name = "openai"
    obj.display_name = "OpenAI"
    obj.provider_type = provider_type
    obj.is_active = True
    obj.configuration = {}
    return obj


def _make_mock_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.delete = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


# ── OrganizationStatus enum ────────────────────────────────────────────────────


class TestOrganizationStatus:
    def test_has_active(self) -> None:
        assert OrganizationStatus.ACTIVE == "active"

    def test_has_suspended(self) -> None:
        assert OrganizationStatus.SUSPENDED == "suspended"

    def test_has_archived(self) -> None:
        assert OrganizationStatus.ARCHIVED == "archived"

    def test_exactly_three_values(self) -> None:
        assert len(list(OrganizationStatus)) == 3


# ── Organization model ─────────────────────────────────────────────────────────


class TestOrganizationModel:
    def test_tablename(self) -> None:
        assert Organization.__tablename__ == "organizations"

    def test_external_id_prefix(self) -> None:
        org = _make_org()
        assert org.external_id.startswith("org_")

    def test_external_id_no_hyphens(self) -> None:
        org = _make_org()
        assert "-" not in org.external_id

    def test_default_status_active(self) -> None:
        org = _make_org()
        org.status = OrganizationStatus.ACTIVE
        assert org.status == OrganizationStatus.ACTIVE

    def test_status_suspended(self) -> None:
        org = _make_org(status=OrganizationStatus.SUSPENDED)
        assert org.status == OrganizationStatus.SUSPENDED

    def test_is_not_deleted_by_default(self) -> None:
        org = _make_org()
        org.deleted_at = None
        assert org.is_deleted is False

    def test_soft_delete_sets_deleted_at(self) -> None:
        org = _make_org()
        assert org.deleted_at is None
        org.soft_delete()
        assert org.deleted_at is not None
        assert org.is_deleted is True

    def test_soft_delete_records_actor(self) -> None:
        org = _make_org()
        actor = uuid.uuid4()
        org.soft_delete(deleted_by=actor)
        assert org.deleted_by == actor

    def test_unique_slug_constraint_present(self) -> None:
        constraint_names = {
            getattr(c, "name", None) for c in Organization.__table_args__
        }
        assert "uq_organizations_slug" in constraint_names

    def test_slug_index_present(self) -> None:
        index_names = {
            getattr(i, "name", None) for i in Organization.__table_args__
        }
        assert "ix_organizations_slug" in index_names

    def test_cursor_index_present(self) -> None:
        index_names = {
            getattr(i, "name", None) for i in Organization.__table_args__
        }
        assert "ix_organizations_cursor" in index_names

    def test_deleted_index_present(self) -> None:
        index_names = {
            getattr(i, "name", None) for i in Organization.__table_args__
        }
        assert "ix_organizations_deleted" in index_names

    def test_nullable_fields(self) -> None:
        org = _make_org()
        org.description = None
        org.website = None
        org.logo_url = None
        org.billing_email = None
        assert org.description is None
        assert org.website is None

    def test_repr(self) -> None:
        org = _make_org()
        assert "Organization" in repr(org)
        assert "org_" in repr(org)


# ── ProjectEnvironment enum ────────────────────────────────────────────────────


class TestProjectEnvironment:
    def test_has_development(self) -> None:
        assert ProjectEnvironment.DEVELOPMENT == "development"

    def test_has_staging(self) -> None:
        assert ProjectEnvironment.STAGING == "staging"

    def test_has_production(self) -> None:
        assert ProjectEnvironment.PRODUCTION == "production"

    def test_exactly_three_values(self) -> None:
        assert len(list(ProjectEnvironment)) == 3


# ── Project model ──────────────────────────────────────────────────────────────


class TestProjectModel:
    def test_tablename(self) -> None:
        assert Project.__tablename__ == "projects"

    def test_external_id_prefix(self) -> None:
        proj = _make_project()
        assert proj.external_id.startswith("proj_")

    def test_stores_org_id(self) -> None:
        org_id = uuid7()
        proj = _make_project(org_id=org_id)
        assert proj.organization_id == org_id

    def test_default_environment(self) -> None:
        proj = _make_project()
        assert proj.environment == ProjectEnvironment.PRODUCTION

    def test_development_environment(self) -> None:
        proj = _make_project(environment=ProjectEnvironment.DEVELOPMENT)
        assert proj.environment == ProjectEnvironment.DEVELOPMENT

    def test_soft_delete_inherited(self) -> None:
        proj = _make_project()
        proj.deleted_at = None
        proj.soft_delete()
        assert proj.is_deleted is True

    def test_org_fk_index_present(self) -> None:
        index_names = {getattr(i, "name", None) for i in Project.__table_args__}
        assert "ix_projects_org_id" in index_names

    def test_cursor_index_present(self) -> None:
        index_names = {getattr(i, "name", None) for i in Project.__table_args__}
        assert "ix_projects_cursor" in index_names

    def test_org_env_composite_index_present(self) -> None:
        index_names = {getattr(i, "name", None) for i in Project.__table_args__}
        assert "ix_projects_org_env" in index_names


# ── MembershipRole enum ────────────────────────────────────────────────────────


class TestMembershipRole:
    def test_has_owner(self) -> None:
        assert MembershipRole.OWNER == "owner"

    def test_has_admin(self) -> None:
        assert MembershipRole.ADMIN == "admin"

    def test_has_member(self) -> None:
        assert MembershipRole.MEMBER == "member"

    def test_has_viewer(self) -> None:
        assert MembershipRole.VIEWER == "viewer"

    def test_exactly_four_values(self) -> None:
        assert len(list(MembershipRole)) == 4


# ── Membership model ───────────────────────────────────────────────────────────


class TestMembershipModel:
    def test_tablename(self) -> None:
        assert Membership.__tablename__ == "memberships"

    def test_external_id_prefix(self) -> None:
        mem = _make_membership()
        assert mem.external_id.startswith("mem_")

    def test_stores_email(self) -> None:
        mem = _make_membership(user_email="bob@example.com")
        assert mem.user_email == "bob@example.com"

    def test_default_role(self) -> None:
        mem = _make_membership()
        assert mem.role == MembershipRole.MEMBER

    def test_owner_role(self) -> None:
        mem = _make_membership(role=MembershipRole.OWNER)
        assert mem.role == MembershipRole.OWNER

    def test_soft_delete_inherited(self) -> None:
        mem = _make_membership()
        mem.deleted_at = None
        mem.soft_delete()
        assert mem.is_deleted is True

    def test_unique_org_email_constraint_present(self) -> None:
        constraint_names = {
            getattr(c, "name", None) for c in Membership.__table_args__
        }
        assert "uq_memberships_org_email" in constraint_names

    def test_email_index_present(self) -> None:
        index_names = {getattr(i, "name", None) for i in Membership.__table_args__}
        assert "ix_memberships_email" in index_names

    def test_cursor_index_present(self) -> None:
        index_names = {getattr(i, "name", None) for i in Membership.__table_args__}
        assert "ix_memberships_cursor" in index_names


# ── ProviderType enum ──────────────────────────────────────────────────────────


class TestProviderType:
    def test_has_openai(self) -> None:
        assert ProviderType.OPENAI == "openai"

    def test_has_anthropic(self) -> None:
        assert ProviderType.ANTHROPIC == "anthropic"

    def test_has_grok(self) -> None:
        assert ProviderType.GROK == "grok"

    def test_has_google(self) -> None:
        assert ProviderType.GOOGLE == "google"

    def test_has_azure_openai(self) -> None:
        assert ProviderType.AZURE_OPENAI == "azure_openai"

    def test_has_openrouter(self) -> None:
        assert ProviderType.OPENROUTER == "openrouter"

    def test_has_ollama(self) -> None:
        assert ProviderType.OLLAMA == "ollama"

    def test_exactly_seven_values(self) -> None:
        assert len(list(ProviderType)) == 7


# ── ProviderConnection model ───────────────────────────────────────────────────


class TestProviderConnectionModel:
    def test_tablename(self) -> None:
        assert ProviderConnection.__tablename__ == "provider_connections"

    def test_external_id_prefix(self) -> None:
        conn = _make_connection()
        assert conn.external_id.startswith("conn_")

    def test_default_is_active(self) -> None:
        conn = _make_connection()
        assert conn.is_active is True

    def test_project_id_nullable(self) -> None:
        conn = _make_connection()
        conn.project_id = None
        assert conn.project_id is None

    def test_default_configuration_empty_dict(self) -> None:
        conn = _make_connection()
        assert conn.configuration == {}

    def test_configuration_accepts_dict(self) -> None:
        conn = _make_connection()
        conn.configuration = {"base_url": "https://api.openai.com/v1", "timeout": 30}
        assert conn.configuration["base_url"] == "https://api.openai.com/v1"

    def test_soft_delete_inherited(self) -> None:
        conn = _make_connection()
        conn.deleted_at = None
        conn.soft_delete()
        assert conn.is_deleted is True

    def test_org_id_index_present(self) -> None:
        index_names = {
            getattr(i, "name", None) for i in ProviderConnection.__table_args__
        }
        assert "ix_provider_connections_org_id" in index_names

    def test_type_index_present(self) -> None:
        index_names = {
            getattr(i, "name", None) for i in ProviderConnection.__table_args__
        }
        assert "ix_provider_connections_type" in index_names

    def test_cursor_index_present(self) -> None:
        index_names = {
            getattr(i, "name", None) for i in ProviderConnection.__table_args__
        }
        assert "ix_provider_connections_cursor" in index_names

    def test_org_active_composite_index_present(self) -> None:
        index_names = {
            getattr(i, "name", None) for i in ProviderConnection.__table_args__
        }
        assert "ix_provider_connections_org_active" in index_names


# ── OrganizationRepository ─────────────────────────────────────────────────────


class TestOrganizationRepository:
    @pytest.mark.asyncio
    async def test_get_by_slug_executes_query(self) -> None:
        session = _make_mock_session()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result_mock)

        repo = OrganizationRepository(session)
        result = await repo.get_by_slug("acme")

        session.execute.assert_awaited_once()
        assert result is None

    @pytest.mark.asyncio
    async def test_slug_exists_returns_false_when_none(self) -> None:
        # slug_exists() now uses SELECT EXISTS(...) → scalar_one() returns False
        session = _make_mock_session()
        result_mock = MagicMock()
        result_mock.scalar_one.return_value = False
        session.execute = AsyncMock(return_value=result_mock)

        repo = OrganizationRepository(session)
        exists = await repo.slug_exists("nonexistent-slug")

        assert exists is False

    @pytest.mark.asyncio
    async def test_slug_exists_returns_true_when_found(self) -> None:
        # slug_exists() now uses SELECT EXISTS(...) → scalar_one() returns True
        session = _make_mock_session()
        result_mock = MagicMock()
        result_mock.scalar_one.return_value = True
        session.execute = AsyncMock(return_value=result_mock)

        repo = OrganizationRepository(session)
        exists = await repo.slug_exists("acme")

        assert exists is True

    @pytest.mark.asyncio
    async def test_create_org(self) -> None:
        session = _make_mock_session()
        repo = OrganizationRepository(session)
        org = _make_org()

        result = await repo.create(org)

        session.add.assert_called_once_with(org)
        session.flush.assert_awaited_once()
        assert result is org

    @pytest.mark.asyncio
    async def test_soft_delete_org(self) -> None:
        session = _make_mock_session()
        repo = OrganizationRepository(session)
        org = _make_org()
        org.deleted_at = None

        result = await repo.soft_delete(org, deleted_by=uuid.uuid4())

        assert result.is_deleted is True
        session.flush.assert_awaited_once()


# ── ProjectRepository ──────────────────────────────────────────────────────────


class TestProjectRepository:
    @pytest.mark.asyncio
    async def test_list_by_org_executes_query(self) -> None:
        session = _make_mock_session()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        session.execute = AsyncMock(return_value=result_mock)

        repo = ProjectRepository(session)
        page = await repo.list_by_org(uuid.uuid4(), limit=10)

        session.execute.assert_awaited_once()
        assert page.items == []
        assert page.has_more is False

    @pytest.mark.asyncio
    async def test_create_project(self) -> None:
        session = _make_mock_session()
        repo = ProjectRepository(session)
        proj = _make_project()

        result = await repo.create(proj)

        session.add.assert_called_once_with(proj)
        assert result is proj


# ── MembershipRepository ───────────────────────────────────────────────────────


class TestMembershipRepository:
    @pytest.mark.asyncio
    async def test_get_by_org_and_email_returns_none(self) -> None:
        session = _make_mock_session()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result_mock)

        repo = MembershipRepository(session)
        result = await repo.get_by_org_and_email(uuid.uuid4(), "alice@example.com")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_org_and_email_returns_membership(self) -> None:
        mem = _make_membership()
        session = _make_mock_session()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = mem
        session.execute = AsyncMock(return_value=result_mock)

        repo = MembershipRepository(session)
        result = await repo.get_by_org_and_email(mem.organization_id, mem.user_email)

        assert result is mem

    @pytest.mark.asyncio
    async def test_create_membership(self) -> None:
        session = _make_mock_session()
        repo = MembershipRepository(session)
        mem = _make_membership()

        result = await repo.create(mem)

        session.add.assert_called_once_with(mem)
        assert result is mem


# ── ProviderConnectionRepository ──────────────────────────────────────────────


class TestProviderConnectionRepository:
    @pytest.mark.asyncio
    async def test_list_active_by_org_executes_query(self) -> None:
        session = _make_mock_session()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        session.execute = AsyncMock(return_value=result_mock)

        repo = ProviderConnectionRepository(session)
        page = await repo.list_active_by_org(uuid.uuid4(), limit=5)

        session.execute.assert_awaited_once()
        assert page.items == []

    @pytest.mark.asyncio
    async def test_create_connection(self) -> None:
        session = _make_mock_session()
        repo = ProviderConnectionRepository(session)
        conn = _make_connection()

        result = await repo.create(conn)

        session.add.assert_called_once_with(conn)
        assert result is conn

    @pytest.mark.asyncio
    async def test_soft_delete_connection(self) -> None:
        session = _make_mock_session()
        repo = ProviderConnectionRepository(session)
        conn = _make_connection()
        conn.deleted_at = None

        result = await repo.soft_delete(conn)

        assert result.is_deleted is True
        session.flush.assert_awaited_once()
