"""
Integration tests — database connectivity and migration verification.

These tests verify:
  - The database is reachable
  - init_db() works correctly
  - All EP-03 tables exist after migration
  - All EP-03 enum types exist
  - All expected indexes are present
  - alembic_version matches the current migration head (not pinned to EP-03)

Skipped when DATABASE_URL is not set.
"""

from __future__ import annotations

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.init_db import init_db
from tests.integration.conftest import requires_db


@requires_db
@pytest.mark.integration
class TestDatabaseConnectivity:
    async def test_init_db_succeeds(
        self, integration_engine: AsyncEngine, run_migrations: str
    ) -> None:
        """
        init_db() must not raise when the database is reachable.

        Depends on run_migrations so this runs against an already-migrated
        database — matching how init_db() is actually invoked in production
        (after deploy, once Alembic has run) — and exercising its intended
        no-op path (create_schema_if_empty() must not attempt
        Base.metadata.create_all() when tables already exist, which would
        collide with the Alembic-managed schema).
        """
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
            result = await conn.run_sync(lambda c: inspect(c).get_table_names())
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

    async def test_alembic_version_matches_head(
        self, integration_engine: AsyncEngine, run_migrations: str
    ) -> None:
        """The alembic_version table must contain the current migration head."""
        from pathlib import Path

        from alembic.config import Config
        from alembic.script import ScriptDirectory

        backend_dir = Path(__file__).parent.parent.parent
        alembic_cfg = Config(str(backend_dir / "migrations" / "alembic.ini"))
        alembic_cfg.set_main_option("script_location", str(backend_dir / "migrations"))
        script = ScriptDirectory.from_config(alembic_cfg)
        expected_head = script.get_current_head()

        async with integration_engine.connect() as conn:
            result = await conn.execute(text("SELECT version_num FROM alembic_version"))
        version = result.scalar_one_or_none()
        assert version == expected_head
