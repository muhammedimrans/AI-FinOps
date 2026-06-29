from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated, Any

from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import Settings, get_settings
from app.core.container import AppContainer


def get_container(request: Request) -> AppContainer:
    """Extract the AppContainer from app state. Available after lifespan startup."""
    container: AppContainer = request.app.state.container
    return container


async def get_db(
    container: Annotated[AppContainer, Depends(get_container)],
) -> AsyncGenerator[AsyncSession]:
    """Yield a database session. Commits on success, rolls back on exception."""
    async with container.session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_redis(
    container: Annotated[AppContainer, Depends(get_container)],
) -> Redis[Any]:
    """Return the shared Redis client from the container."""
    return container.redis


# Convenience type aliases for use in routers
ContainerDep = Annotated[AppContainer, Depends(get_container)]
DbDep = Annotated[AsyncSession, Depends(get_db)]
RedisDep = Annotated[Redis, Depends(get_redis)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
