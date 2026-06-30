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


async def create_schema_if_empty(engine: AsyncEngine) -> None:
    """
    Create all ORM tables on an empty database.

    Uses checkfirst=True so existing tables are never dropped or modified.
    Imports app.models to ensure every model is registered in Base.metadata
    before create_all runs.
    """
    import app.models  # noqa: F401 — registers all ORM models in Base.metadata
    from app.db.base import Base

    async with engine.begin() as conn:
        has_tables = await conn.run_sync(_has_tables)
        if has_tables:
            logger.debug("schema_exists", hint="skipping create_all")
            return

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
