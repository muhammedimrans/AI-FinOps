from __future__ import annotations

import time
from dataclasses import dataclass

import structlog
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.config.settings import Settings
from app.core.database import create_engine, create_session_factory
from app.core.redis import create_redis
from app.db.init_db import init_db
from app.db.seed import seed_startup_data
from app.realtime.connection_manager import ConnectionManager
from app.realtime.event_bus import EventBus
from app.realtime.metrics import events_dispatched_total, events_dropped_total
from app.realtime.rate_limit import ConnectionRateLimiter
from app.services.usage_sync_scheduler import UsageSyncScheduler

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
    redis: Redis
    event_bus: EventBus
    connection_manager: ConnectionManager
    realtime_rate_limiter: ConnectionRateLimiter
    # Optional so pre-EP-23.4 call sites that build AppContainer directly
    # (see tests/test_ep19_1.py's _mock_container) keep working unmodified.
    usage_sync_scheduler: UsageSyncScheduler | None = None

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

        # Verify connectivity and create schema if the database is empty.
        # create_schema_if_empty() uses Base.metadata.create_all(checkfirst=True)
        # so it is a no-op when tables already exist.
        await init_db(engine)

        # Seed demo data on first startup; single-SELECT no-op on subsequent starts.
        await seed_startup_data(session_factory)

        event_bus = EventBus(redis)
        connection_manager = ConnectionManager(event_bus)
        connection_manager.on_dispatch(lambda _info, _event: events_dispatched_total.inc())
        connection_manager.on_drop(lambda _info: events_dropped_total.inc())
        connection_manager.start()
        realtime_rate_limiter = ConnectionRateLimiter(redis=redis)

        usage_sync_scheduler = UsageSyncScheduler(
            session_factory,
            redis=redis,
            tick_interval_seconds=settings.scheduler_tick_interval_seconds,
        )
        if settings.scheduler_enabled:
            await usage_sync_scheduler.start()

        elapsed_ms = round((time.monotonic() - start) * 1000, 2)
        logger.info("container_ready", startup_ms=elapsed_ms)

        return cls(
            settings=settings,
            engine=engine,
            session_factory=session_factory,
            redis=redis,
            event_bus=event_bus,
            connection_manager=connection_manager,
            realtime_rate_limiter=realtime_rate_limiter,
            usage_sync_scheduler=usage_sync_scheduler,
        )

    async def close(self) -> None:
        """Release all resources gracefully."""
        logger.info("container_closing")
        if self.usage_sync_scheduler is not None:
            await self.usage_sync_scheduler.stop()
        await self.connection_manager.stop()
        await self.engine.dispose()
        await self.redis.close()
        logger.info("container_closed")
