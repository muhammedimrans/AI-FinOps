"""
Database initialization helpers.

Called once at application startup (via AppContainer.create) to verify
connectivity and log the database version. Schema creation is managed
entirely by Alembic — this module never calls Base.metadata.create_all().
"""

from __future__ import annotations

import time

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = structlog.get_logger(__name__)


async def verify_database(engine: AsyncEngine) -> str:
    """
    Verify the database is reachable and return its version string.
    Raises on failure so the application refuses to start with a bad DB.
    """
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT version()"))
        version: str = result.scalar_one()
    return version


async def init_db(engine: AsyncEngine) -> None:
    """
    Application startup hook for database readiness.

    Verifies connectivity and logs the PostgreSQL version. Raises on any
    connection failure so the application fails fast rather than starting
    in a degraded state.

    Schema management is handled entirely by Alembic migrations:
      alembic upgrade head
    This function never calls Base.metadata.create_all().
    """
    start = time.monotonic()
    try:
        version = await verify_database(engine)
        elapsed_ms = round((time.monotonic() - start) * 1000, 2)
        logger.info(
            "database_connected",
            pg_version=version.split(",")[0],  # e.g. "PostgreSQL 16.1"
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
