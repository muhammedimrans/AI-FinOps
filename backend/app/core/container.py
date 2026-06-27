from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.config.settings import Settings
from app.core.database import create_engine, create_session_factory
from app.core.redis import create_redis


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

    @classmethod
    async def create(cls, settings: Settings) -> AppContainer:
        """
        Initialise all resources.
        Engine and Redis pool creation is lazy — no network IO happens here.
        """
        engine = create_engine(
            settings.database_url,
            echo=settings.app_debug,
        )
        session_factory = create_session_factory(engine)
        redis = create_redis(settings.redis_url)

        return cls(
            settings=settings,
            engine=engine,
            session_factory=session_factory,
            redis=redis,
        )

    async def close(self) -> None:
        """Release all resources gracefully."""
        await self.engine.dispose()
        await self.redis.aclose()
