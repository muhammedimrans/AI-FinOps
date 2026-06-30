"""
Database initialization helpers.

Called once at application startup (via AppContainer.create) to verify
connectivity, create the schema if the database is empty, and log the
database version.

Schema strategy
---------------
Alembic migrations live in migrations/versions/ and remain the
authoritative schema definition.  On a fresh database (no tables at all)
we call Base.metadata.create_all(checkfirst=True) so the application can
start without requiring a separate migration step.  On an already-migrated
database create_all is a safe no-op — it never drops or alters existing
tables.
"""

from __future__ import annotations

import time

import structlog
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

logger = structlog.get_logger(__name__)


async def verify_database(engine: AsyncEngine) -> str:
    """Return the PostgreSQL version string; raises if unreachable."""
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT version()"))
        version: str = result.scalar_one()
    return version


def _has_tables(conn: AsyncConnection) -> bool:  # called via run_sync
    inspector = inspect(conn)
    return bool(inspector.get_table_names(schema="public"))


def _drop_stale_enum_types(conn: AsyncConnection) -> None:  # called via run_sync
    """
    Drop any PostgreSQL enum types that were left behind by a previously
    failed create_all() run.  Safe to call only when no tables exist, because
    no column can reference these types at that point.

    Prior to the values_callable fix, SQLAlchemy created enums using
    member names (e.g. 'ACTIVE') rather than member values ('active').
    Those stale uppercase types would cause the corrected create_all() to
    skip re-creating them (checkfirst) and then fail when server_default
    values or INSERT data used the lowercase form.
    """
    result = conn.execute(
        text(
            "SELECT typname FROM pg_type "
            "JOIN pg_namespace ON pg_namespace.oid = pg_type.typnamespace "
            "WHERE pg_type.typtype = 'e' AND pg_namespace.nspname = 'public'"
        )
    )
    enum_names = [row[0] for row in result]
    for name in enum_names:
        conn.execute(text(f'DROP TYPE IF EXISTS "{name}" CASCADE'))  # noqa: S608
        logger.info("schema_dropped_stale_enum", enum=name)


async def create_schema_if_empty(engine: AsyncEngine) -> None:
    """
    Create all ORM tables on an empty database.

    When the database has no tables, any pre-existing enum types are dropped
    first (they may have been created with incorrect uppercase values by an
    earlier failed run) so create_all() recreates them correctly.

    On a database that already has tables, this function is a no-op.
    """
    import app.models  # noqa: F401 — registers all ORM models in Base.metadata
    from app.db.base import Base

    async with engine.begin() as conn:
        has_tables = await conn.run_sync(_has_tables)
        if has_tables:
            logger.debug("schema_exists", hint="skipping create_all")
            return

        # Drop any stale enum types from a previous failed create_all() run.
        await conn.run_sync(_drop_stale_enum_types)

        logger.info("schema_creating", hint="empty database — running Base.metadata.create_all()")
        await conn.run_sync(Base.metadata.create_all)
        logger.info("schema_created")


async def init_db(engine: AsyncEngine) -> None:
    """
    Application startup hook: verify connectivity then ensure schema exists.

    Raises on any connection failure so the process exits cleanly rather
    than starting in a degraded state.
    """
    start = time.monotonic()
    try:
        version = await verify_database(engine)
        elapsed_ms = round((time.monotonic() - start) * 1000, 2)
        logger.info(
            "database_connected",
            pg_version=version.split(",")[0],
            latency_ms=elapsed_ms,
        )
    except Exception as exc:
        elapsed_ms = round((time.monotonic() - start) * 1000, 2)
        logger.error(
            "database_connection_failed",
            error=str(exc),
            latency_ms=elapsed_ms,
        )
        raise

    await create_schema_if_empty(engine)
