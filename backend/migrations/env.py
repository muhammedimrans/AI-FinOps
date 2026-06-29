from __future__ import annotations

import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

# Ensure the backend/ directory is on sys.path so `app` is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config.settings import get_settings
from app.db.base import Base
import app.db.mixins  # noqa: F401 — registers BaseModel in Base.metadata
import app.models  # noqa: F401 — future business models register here

# Alembic Config object provides access to .ini values
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Offline mode: generate SQL without a live DB connection.
    Useful for reviewing migration SQL before applying.
    """
    settings = get_settings()
    url = settings.database_url_sync

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """
    Online mode: connect to the database and apply migrations.
    Uses the async engine because SQLAlchemy 2.x asyncpg doesn't support
    synchronous connections at the driver level.
    """
    settings = get_settings()

    connectable = create_async_engine(
        settings.database_url,
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
