"""Per-IP connection-attempt rate limiting — EP-19.1.

A minimal sliding-window limiter for WS/SSE connection *attempts*,
independent of `app.auth.rate_limit.LoginRateLimiter` (which has
login-specific semantics — per-account exponential lockout — that don't
apply to opening a streaming connection). Mirrors the same
Redis-with-in-memory-fallback shape as that module for consistency: Redis
when available (so the limit applies across API replicas), degrading to a
per-process in-memory count on any Redis error rather than failing open or
taking connection handling down with Redis.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import structlog

log = structlog.get_logger(__name__)

WINDOW_SECONDS = 60
MAX_ATTEMPTS_PER_IP = 30


@dataclass
class _MemoryWindow:
    _hits: dict[str, list[float]] = field(default_factory=dict)

    def count_and_add(self, key: str, now: float, window: int) -> int:
        hits = [t for t in self._hits.get(key, []) if t > now - window]
        hits.append(now)
        self._hits[key] = hits
        return len(hits)


@dataclass
class ConnectionRateLimiter:
    redis: Any = None  # redis.asyncio.Redis | None
    window_seconds: int = WINDOW_SECONDS
    max_attempts: int = MAX_ATTEMPTS_PER_IP
    _memory: _MemoryWindow = field(default_factory=_MemoryWindow)

    async def check(self, *, ip: str | None) -> bool:
        """Returns True if a new connection attempt from `ip` is allowed.
        A missing `ip` (e.g. in a test harness with no client address) is
        always allowed — there is nothing to key the limit on."""
        if not ip:
            return True
        now = time.time()
        key = f"rl:realtime:conn:{ip}"

        if self.redis is not None:
            try:
                pipe = self.redis.pipeline()
                pipe.zremrangebyscore(key, 0, now - self.window_seconds)
                pipe.zadd(key, {f"{now!r}": now})
                pipe.zcard(key)
                pipe.expire(key, self.window_seconds * 2)
                results = await pipe.execute()
                count = int(results[2])
                return count <= self.max_attempts
            except Exception:
                log.warning("realtime_rate_limit_redis_degraded", exc_info=True)

        count = self._memory.count_and_add(key, now, self.window_seconds)
        return count <= self.max_attempts
