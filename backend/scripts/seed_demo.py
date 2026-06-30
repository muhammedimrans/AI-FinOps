#!/usr/bin/env python3
"""
Standalone runner for the idempotent demo-data seed.

The seed logic lives in app/db/seed.py and is also called automatically at
every application startup. Run this script directly only when you need to seed
outside of a running server (e.g. against a fresh database before first deploy).

Usage:
  cd backend
  python -m scripts.seed_demo
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Allow running as: python -m scripts.seed_demo from backend/
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config.settings import get_settings
from app.db.seed import seed_demo_data


async def main() -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url), echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    print("Seeding demo data…")
    async with session_factory() as session:
        await seed_demo_data(session)

    await engine.dispose()
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
