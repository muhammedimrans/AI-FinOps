"""
FastAPI database session dependency.

Usage in a route::

    from fastapi import Depends
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.db.dependencies import get_session

    @router.get("/items")
    async def list_items(session: AsyncSession = Depends(get_session)):
        ...

In practice the dependency is wired via the AppContainer so routes receive
a pre-bound partial rather than importing get_session directly.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def get_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession]:
    """
    Async generator that yields a database session.
    Commits on clean exit; rolls back on any exception.

    Intended for use as a FastAPI dependency via functools.partial or
    AppContainer injection.
    """
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
