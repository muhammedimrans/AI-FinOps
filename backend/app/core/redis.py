from __future__ import annotations

from typing import Any

from redis.asyncio import Redis


def create_redis(redis_url: str) -> Redis[Any]:
    """
    Create a Redis connection pool from a URL.
    Connection is lazy — no socket opened until first command.
    """
    return Redis.from_url(
        redis_url,
        encoding="utf-8",
        decode_responses=False,
        socket_connect_timeout=5,
        socket_timeout=5,
        retry_on_timeout=True,
        health_check_interval=30,
    )


async def check_redis(redis: Redis[Any]) -> dict[str, Any]:
    """
    Ping Redis. Returns a health-check result dict.
    Does not raise — callers decide how to handle failures.
    """
    import time

    start = time.monotonic()
    try:
        await redis.ping()
        latency_ms = round((time.monotonic() - start) * 1000, 2)
        return {"status": "healthy", "latency_ms": latency_ms}
    except Exception as exc:
        return {"status": "unhealthy", "latency_ms": None, "error": str(exc)}
