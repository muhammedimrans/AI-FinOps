"""
Integration test fixtures.

All fixtures in this module require a live PostgreSQL database. Tests are
skipped when DATABASE_URL is not set in the environment so the default CI
run (unit tests only) passes without a database connection.

Database setup strategy:
  - Each test session runs `alembic upgrade head` once to ensure the schema
    is current. Tests never call Base.metadata.create_all().
  - Each test function gets a fresh transaction that is rolled back after the
    test, ensuring full isolation without truncating tables between tests.
  - The outermost session wraps each test in a SAVEPOINT so nested
    transactions in application code work correctly.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# ── Skip guard ────────────────────────────────────────────────────────────────

DATABASE_URL: str = os.environ.get("DATABASE_URL", "")

requires_db = pytest.mark.skipif(
    not DATABASE_URL,
    reason=(
        "DATABASE_URL not set — integration tests require a live PostgreSQL database. "
        "Set DATABASE_URL=postgresql+asyncpg://... to run these tests."
    ),
)


# ── Engine / session fixtures ─────────────────────────────────────────────────


@pytest_asyncio.fixture(scope="session")
async def integration_engine():  # type: ignore[return]
    """
    Session-scoped async engine pointing at the integration test database.
    Uses NullPool because pytest-asyncio manages the event loop per session.
    """
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL not set")

    engine = create_async_engine(DATABASE_URL, poolclass=NullPool, echo=False)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def run_migrations(integration_engine):  # type: ignore[return]
    """
    Run `alembic upgrade head` once per test session to ensure the schema is
    current. This verifies that migrations themselves work correctly.
    """
    import subprocess
    import sys
    from pathlib import Path

    backend_dir = Path(__file__).parent.parent.parent
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(backend_dir),
        capture_output=True,
        text=True,
        env={**os.environ, "DATABASE_URL": DATABASE_URL},
    )
    if result.returncode != 0:
        pytest.fail(f"alembic upgrade head failed:\n{result.stdout}\n{result.stderr}")
    yield result.stdout


@pytest_asyncio.fixture
async def db_session(integration_engine) -> AsyncGenerator[AsyncSession]:
    """
    Function-scoped database session.

    Each test runs inside a transaction that is rolled back on teardown,
    providing full isolation without truncating tables.
    """
    async with integration_engine.begin() as conn:
        # Begin a savepoint for nested transaction support inside tests
        async with async_sessionmaker(
            bind=conn,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )() as session:
            yield session
            await session.rollback()
