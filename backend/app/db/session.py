"""
Async session factory and transaction context manager.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Return an async session factory bound to the given engine."""
    return async_sessionmaker(
        engine,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


@asynccontextmanager
async def managed_transaction(
    session: AsyncSession,
) -> AsyncGenerator[AsyncSession]:
    """
    Explicit nested transaction context manager for use outside FastAPI DI —
    e.g. background jobs, batch processing, or service-layer helpers that need
    explicit BEGIN / COMMIT / ROLLBACK control within an already-open session.

    Usage::

        async with managed_transaction(session) as txn:
            await repo.create(...)
            await other_repo.update(...)
        # commits here; rolls back on exception
    """
    async with session.begin_nested():
        yield session
