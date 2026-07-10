from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi import status as http_status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import Settings, get_settings
from app.core.container import AppContainer
from app.realtime.connection_manager import ConnectionManager
from app.realtime.event_bus import EventBus
from app.realtime.rate_limit import ConnectionRateLimiter
from app.services.usage_sync_scheduler import UsageSyncScheduler


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
) -> Redis:
    """Return the shared Redis client from the container."""
    return container.redis


def get_event_bus(
    container: Annotated[AppContainer, Depends(get_container)],
) -> EventBus:
    """Return the shared real-time event bus from the container."""
    return container.event_bus


def get_connection_manager(
    container: Annotated[AppContainer, Depends(get_container)],
) -> ConnectionManager:
    """Return the shared real-time connection manager from the container."""
    return container.connection_manager


def get_realtime_rate_limiter(
    container: Annotated[AppContainer, Depends(get_container)],
) -> ConnectionRateLimiter:
    """Return the shared real-time connection-attempt rate limiter."""
    return container.realtime_rate_limiter


def get_usage_sync_scheduler(
    container: Annotated[AppContainer, Depends(get_container)],
) -> UsageSyncScheduler:
    """Return the shared background usage-sync scheduler (EP-23.4).

    Raises 503 rather than a bare AttributeError/None-dereference on the
    (only ever test-authored, see AppContainer's own docstring) code path
    where a container was built without one.
    """
    if container.usage_sync_scheduler is None:
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Background sync scheduler is not available.",
        )
    return container.usage_sync_scheduler


# Convenience type aliases for use in routers
ContainerDep = Annotated[AppContainer, Depends(get_container)]
DbDep = Annotated[AsyncSession, Depends(get_db)]
RedisDep = Annotated[Redis, Depends(get_redis)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
EventBusDep = Annotated[EventBus, Depends(get_event_bus)]
ConnectionManagerDep = Annotated[ConnectionManager, Depends(get_connection_manager)]
RealtimeRateLimiterDep = Annotated[ConnectionRateLimiter, Depends(get_realtime_rate_limiter)]
SchedulerDep = Annotated[UsageSyncScheduler, Depends(get_usage_sync_scheduler)]
