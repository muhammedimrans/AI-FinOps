"""
Async SQLAlchemy engine factory and database health check.

The engine is created once at application startup via AppContainer and held
for the lifetime of the process. Connection is lazy — no socket is opened
until the first query.
"""
from __future__ import annotations

import time
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def create_engine(database_url: str, *, echo: bool = False) -> AsyncEngine:
    """
    Create and configure the async SQLAlchemy engine.

    Pool settings are tuned for Neon PostgreSQL serverless:
      pool_pre_ping   — discard stale connections after idle
      pool_recycle    — recycle connections older than 30 minutes
    """
    return create_async_engine(
        database_url,
        echo=echo,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        pool_timeout=30,
        pool_recycle=1800,
    )


async def check_database(engine: AsyncEngine) -> dict[str, Any]:
    """
    Ping the database. Returns a health-check result dict.
    Does not raise — callers decide how to handle failures.
    """
    start = time.monotonic()
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        latency_ms = round((time.monotonic() - start) * 1000, 2)
        return {"status": "healthy", "latency_ms": latency_ms}
    except Exception as exc:
        return {"status": "unhealthy", "latency_ms": None, "error": str(exc)}
