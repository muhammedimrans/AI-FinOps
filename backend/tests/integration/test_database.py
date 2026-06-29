"""
Integration tests — database connectivity and migration verification.

These tests verify:
  - The database is reachable
  - init_db() works correctly
  - All EP-03 tables exist after migration
  - All EP-03 enum types exist
  - All expected indexes are present

Skipped when DATABASE_URL is not set.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.init_db import init_db
from tests.integration.conftest import requires_db


@requires_db
@pytest.mark.integration
class TestDatabaseConnectivity:
    async def test_init_db_succeeds(self, integration_engine: AsyncEngine) -> None:
        """init_db() must not raise when the database is reachable."""
        await init_db(integration_engine)

    async def test_raw_query_executes(self, integration_engine: AsyncEngine) -> None:
        """Basic SELECT 1 must succeed."""
        async with integration_engine.connect() as conn:
            result = await conn.execute(text("SELECT 1 AS ping"))
            assert result.scalar_one() == 1

    async def test_postgres_version_is_returned(self, integration_engine: AsyncEngine) -> None:
        """SELECT version() must return a non-empty string."""
        async with integration_engine.connect() as conn:
            result = await conn.execute(text("SELECT version()"))
            version = result.scalar_one()
        assert isinstance(version, str)
        assert "PostgreSQL" in version


@requires_db
@pytest.mark.integration
class TestMigrationSchema:
    """Verify the schema produced by EP-03 migration is correct."""

    async def test_organizations_table_exists(
        self, integration_engine: AsyncEngine, run_migrations: str
    ) -> None:
        async with integration_engine.connect() as conn:
            result = await conn.run_sync(
                lambda c: inspect(c).get_table_names()
            )
        assert "organizations" in result

    async def test_projects_table_exists(
        self, integration_engine: AsyncEngine, run_migrations: str
    ) -> None:
        async with integration_engine.connect() as conn:
            tables = await conn.run_sync(lambda c: inspect(c).get_table_names())
        assert "projects" in tables

    async def test_memberships_table_exists(
        self, integration_engine: AsyncEngine, run_migrations: str
    ) -> None:
        async with integration_engine.connect() as conn:
            tables = await conn.run_sync(lambda c: inspect(c).get_table_names())
        assert "memberships" in tables

    async def test_provider_connections_table_exists(
        self, integration_engine: AsyncEngine, run_migrations: str
    ) -> None:
        async with integration_engine.connect() as conn:
            tables = await conn.run_sync(lambda c: inspect(c).get_table_names())
        assert "provider_connections" in tables

    async def test_organization_status_enum_exists(
        self, integration_engine: AsyncEngine, run_migrations: str
    ) -> None:
        async with integration_engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT typname FROM pg_type "
                    "WHERE typtype = 'e' AND typname = 'organization_status'"
                )
            )
        assert result.scalar_one_or_none() == "organization_status"

    async def test_provider_type_enum_exists(
        self, integration_engine: AsyncEngine, run_migrations: str
    ) -> None:
        async with integration_engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT typname FROM pg_type "
                    "WHERE typtype = 'e' AND typname = 'provider_type'"
                )
            )
        assert result.scalar_one_or_none() == "provider_type"

    async def test_organizations_cursor_index_exists(
        self, integration_engine: AsyncEngine, run_migrations: str
    ) -> None:
        async with integration_engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE tablename = 'organizations' "
                    "AND indexname = 'ix_organizations_cursor'"
                )
            )
        assert result.scalar_one_or_none() == "ix_organizations_cursor"

    async def test_alembic_version_matches_ep03(
        self, integration_engine: AsyncEngine, run_migrations: str
    ) -> None:
        """The alembic_version table must contain the EP-03 revision."""
        async with integration_engine.connect() as conn:
            result = await conn.execute(
                text("SELECT version_num FROM alembic_version")
            )
        version = result.scalar_one_or_none()
        assert version == "a3b4c5d6e7f8"
