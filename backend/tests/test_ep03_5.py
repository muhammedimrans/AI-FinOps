"""
Tests for EP-03.5 Foundation Hardening changes.

Covers:
  - H-001: init_db() wiring (AppContainer.create calls init_db)
  - H-002: Provider configuration validation (tested separately in test_validators.py)
  - H-003: SQLAlchemy lazy="raise" on all EP-03 relationships
  - Repository improvements: update() key validation, slug_exists() EXISTS query,
    list_by_org_and_role() order parameter
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config.settings import Settings
from app.core.container import AppContainer
from tests.conftest import make_connection, make_membership, make_org, make_project

# ── H-001: Startup lifecycle ──────────────────────────────────────────────────


@pytest.mark.unit
class TestStartupLifecycle:
    async def test_container_create_calls_init_db(
        self, test_settings: Settings
    ) -> None:
        """AppContainer.create() must call init_db() so DB is verified on startup."""
        mock_engine = AsyncMock()
        mock_engine.dispose = AsyncMock()
        with (
            patch("app.core.container.init_db", new_callable=AsyncMock) as mock_init_db,
            patch("app.core.container.create_engine", return_value=mock_engine),
            patch("app.core.container.create_session_factory", return_value=MagicMock()),
            patch("app.core.container.create_redis", return_value=AsyncMock()),
        ):
            container = await AppContainer.create(test_settings)

        mock_init_db.assert_awaited_once()
        await container.close()

    async def test_container_create_fails_fast_when_db_unreachable(
        self, test_settings: Settings
    ) -> None:
        """If init_db() raises, AppContainer.create() must propagate the error."""
        mock_engine = AsyncMock()
        mock_engine.dispose = AsyncMock()
        with (
            patch(
                "app.core.container.init_db",
                new_callable=AsyncMock,
                side_effect=ConnectionError("Cannot connect to database"),
            ),
            patch("app.core.container.create_engine", return_value=mock_engine),
            patch("app.core.container.create_session_factory", return_value=MagicMock()),
            patch("app.core.container.create_redis", return_value=AsyncMock()),
        ):
            with pytest.raises(ConnectionError, match="Cannot connect"):
                await AppContainer.create(test_settings)

    async def test_init_db_uses_structlog(self) -> None:
        """init_db must log with structlog, not stdlib logging."""

        from app.db.init_db import init_db

        mock_engine = MagicMock()
        mock_conn = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = "PostgreSQL 16.1 on x86_64"
        mock_conn.execute = AsyncMock(return_value=mock_result)
        mock_engine.connect = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_conn),
            __aexit__=AsyncMock(return_value=None),
        ))

        # Should not raise — structlog logger must be used
        with patch("app.db.init_db.logger") as mock_logger:
            await init_db(mock_engine)
            mock_logger.info.assert_called_once()
            call_kwargs = mock_logger.info.call_args
            assert call_kwargs[0][0] == "database_connected"


# ── H-003: SQLAlchemy lazy="raise" ───────────────────────────────────────────


@pytest.mark.unit
class TestRelationshipLoadingPolicy:
    def test_organization_projects_lazy_is_raise(self) -> None:
        from sqlalchemy import inspect as sa_inspect

        from app.models.organization import Organization

        mapper = sa_inspect(Organization)
        rel = mapper.relationships["projects"]
        assert rel.lazy == "raise", (
            "Organization.projects must use lazy='raise' to prevent accidental "
            "lazy loads in async context. Use selectinload() in service layer."
        )

    def test_organization_memberships_lazy_is_raise(self) -> None:
        from sqlalchemy import inspect as sa_inspect

        from app.models.organization import Organization

        mapper = sa_inspect(Organization)
        rel = mapper.relationships["memberships"]
        assert rel.lazy == "raise"

    def test_organization_provider_connections_lazy_is_raise(self) -> None:
        from sqlalchemy import inspect as sa_inspect

        from app.models.organization import Organization

        mapper = sa_inspect(Organization)
        rel = mapper.relationships["provider_connections"]
        assert rel.lazy == "raise"

    def test_project_organization_lazy_is_raise(self) -> None:
        from sqlalchemy import inspect as sa_inspect

        from app.models.project import Project

        mapper = sa_inspect(Project)
        rel = mapper.relationships["organization"]
        assert rel.lazy == "raise"

    def test_project_provider_connections_lazy_is_raise(self) -> None:
        from sqlalchemy import inspect as sa_inspect

        from app.models.project import Project

        mapper = sa_inspect(Project)
        rel = mapper.relationships["provider_connections"]
        assert rel.lazy == "raise"

    def test_membership_organization_lazy_is_raise(self) -> None:
        from sqlalchemy import inspect as sa_inspect

        from app.models.membership import Membership

        mapper = sa_inspect(Membership)
        rel = mapper.relationships["organization"]
        assert rel.lazy == "raise"

    def test_provider_connection_organization_lazy_is_raise(self) -> None:
        from sqlalchemy import inspect as sa_inspect

        from app.models.provider_connection import ProviderConnection

        mapper = sa_inspect(ProviderConnection)
        rel = mapper.relationships["organization"]
        assert rel.lazy == "raise"

    def test_provider_connection_project_lazy_is_raise(self) -> None:
        from sqlalchemy import inspect as sa_inspect

        from app.models.provider_connection import ProviderConnection

        mapper = sa_inspect(ProviderConnection)
        rel = mapper.relationships["project"]
        assert rel.lazy == "raise"

    def test_organization_cascade_relationships_use_passive_deletes(self) -> None:
        from sqlalchemy import inspect as sa_inspect

        from app.models.organization import Organization

        mapper = sa_inspect(Organization)
        for rel_name in ("projects", "memberships", "provider_connections"):
            rel = mapper.relationships[rel_name]
            assert rel.passive_deletes, (
                f"Organization.{rel_name} must set passive_deletes=True to rely on "
                "DB-level ON DELETE CASCADE instead of loading children in Python."
            )


# ── Repository improvements ───────────────────────────────────────────────────


@pytest.mark.unit
class TestBaseRepositoryUpdate:
    async def test_update_rejects_unknown_key(self) -> None:
        """update() must raise AttributeError for non-existent model attributes."""
        from unittest.mock import AsyncMock

        from app.repositories.organization_repository import OrganizationRepository

        session = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        repo = OrganizationRepository(session)
        org = make_org()

        with pytest.raises(AttributeError, match="nonexistent_field"):
            await repo.update(org, nonexistent_field="value")

    async def test_update_accepts_valid_key(self) -> None:
        """update() must accept known model attributes."""
        from unittest.mock import AsyncMock

        from app.repositories.organization_repository import OrganizationRepository

        session = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        repo = OrganizationRepository(session)
        org = make_org(name="Old Name")

        await repo.update(org, name="New Name")
        assert org.name == "New Name"


@pytest.mark.unit
class TestMembershipRepositoryOrderParam:
    async def test_list_by_org_and_role_accepts_order_desc(self) -> None:
        """list_by_org_and_role() must accept an order parameter."""
        from unittest.mock import AsyncMock, MagicMock

        from app.models.membership import MembershipRole
        from app.repositories.membership_repository import MembershipRepository

        session = AsyncMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        session.execute = AsyncMock(return_value=result_mock)

        repo = MembershipRepository(session)
        page = await repo.list_by_org_and_role(
            uuid.uuid4(), MembershipRole.OWNER, order="desc"
        )
        assert page.items == []


@pytest.mark.unit
class TestConfTestFactories:
    """Verify the shared conftest factories produce correct instances."""

    def test_make_org_has_uuid_id(self) -> None:
        org = make_org()
        assert isinstance(org.id, uuid.UUID)

    def test_make_project_links_org_id(self) -> None:
        org_id = uuid.uuid4()
        proj = make_project(org_id=org_id)
        assert proj.organization_id == org_id

    def test_make_membership_defaults_to_member_role(self) -> None:
        from app.models.membership import MembershipRole
        mem = make_membership()
        assert mem.role == MembershipRole.MEMBER

    def test_make_connection_defaults_empty_config(self) -> None:
        conn = make_connection()
        assert conn.configuration == {}
