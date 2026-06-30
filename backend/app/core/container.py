from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import structlog
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.config.settings import Settings
from app.core.database import create_engine, create_session_factory
from app.core.redis import create_redis
from app.db.init_db import init_db
from app.db.seed import seed_startup_data

logger = structlog.get_logger(__name__)


@dataclass
class AppContainer:
    """
    Holds all initialised application-level resources.
    Created once at startup, torn down on shutdown.
    Services and routers receive resources via FastAPI DI (app.state.container).
    """

    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    redis: Redis[Any]

    @classmethod
    async def create(cls, settings: Settings) -> AppContainer:
        """
        Initialise all resources and verify database connectivity.

        Engine and Redis pool creation is lazy (no network IO for engine/redis
        construction), but init_db() performs a live connectivity check against
        PostgreSQL. If the database is unreachable, this method raises and the
        application refuses to start (fail-fast behaviour).
        """
        start = time.monotonic()
        logger.info("container_initializing", env=settings.app_env)

        engine = create_engine(
            settings.database_url,
            echo=settings.app_debug,
        )
        session_factory = create_session_factory(engine)
        redis = create_redis(settings.redis_url)

        # Verify DB connectivity — raises on failure so the process exits cleanly.
        await init_db(engine)

        # Seed demo data on first startup; no-op on subsequent starts.
        await seed_startup_data(session_factory)

        elapsed_ms = round((time.monotonic() - start) * 1000, 2)
        logger.info("container_ready", startup_ms=elapsed_ms)

        return cls(
            settings=settings,
            engine=engine,
            session_factory=session_factory,
            redis=redis,
        )

    async def close(self) -> None:
        """Release all resources gracefully."""
        logger.info("container_closing")
        await self.engine.dispose()
        await self.redis.close()
        logger.info("container_closed")
