#!/usr/bin/env python3
"""Verify the database connection using the configured DATABASE_URL."""
from __future__ import annotations

import asyncio
import sys
import time


async def main() -> None:
    # Import here so the script works from any directory
    sys.path.insert(0, "backend")

    from app.config.settings import get_settings
    from app.core.database import create_engine

    settings = get_settings()
    url = settings.database_url

    # Mask password for display
    masked = url.split("@")
    display_url = f"...@{masked[-1]}" if len(masked) > 1 else url
    print(f"Connecting to: {display_url}")

    engine = create_engine(url, echo=False)
    start = time.monotonic()
    try:
        from sqlalchemy import text

        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT version()"))
            row = result.scalar()
            elapsed = (time.monotonic() - start) * 1000
            print(f"Connected in {elapsed:.1f}ms")
            print(f"Server: {row}")
            print("Database connection OK")
    except Exception as exc:
        elapsed = (time.monotonic() - start) * 1000
        print(f"Connection failed after {elapsed:.1f}ms: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
