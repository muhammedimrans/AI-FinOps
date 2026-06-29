"""
Database initialization helpers.

Called once at application startup (via AppContainer.create) to verify
connectivity and log the database version. Schema creation is managed
entirely by Alembic — this module never calls Base.metadata.create_all().
"""
from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)


async def verify_database(engine: AsyncEngine) -> None:
    """
    Verify the database is reachable and log its version.
    Raises on failure so the application refuses to start with a bad DB.
    """
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT version()"))
        version = result.scalar_one()
    logger.info("Database connected: %s", version)


async def init_db(engine: AsyncEngine) -> None:
    """
    Application startup hook for database readiness.
    In production, Alembic handles all schema changes via `alembic upgrade head`.
    This function only validates connectivity.
    """
    try:
        await verify_database(engine)
    except Exception as exc:
        logger.error("Database initialisation failed: %s", exc)
        raise
