"""Login rate limiting — sliding window + temporary account lockout.

Protects POST /v1/auth/login against credential stuffing and brute force:

  * Per-IP sliding window: at most ``ip_max_attempts`` login attempts per
    ``window_seconds``, successful or not. Blocks distributed guessing from
    a single source.
  * Per-account lockout: after ``account_max_failures`` consecutive failed
    attempts for the same email, the account is temporarily locked with
    exponential backoff (``lockout_base_seconds * 2**(extra failures)``,
    capped at ``lockout_max_seconds``). A successful login resets the count.
    Lockouts are always temporary — never permanent.

Storage is Redis when available so limits apply across API workers. Any
Redis failure degrades gracefully to a per-process in-memory fallback —
rate limiting keeps working (per worker) rather than failing open entirely
or taking login down with Redis.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import structlog

log = structlog.get_logger(__name__)

# ── Policy defaults ────────────────────────────────────────────────────────────

WINDOW_SECONDS = 60
IP_MAX_ATTEMPTS = 10
ACCOUNT_MAX_FAILURES = 5
LOCKOUT_BASE_SECONDS = 30
LOCKOUT_MAX_SECONDS = 900  # 15 minutes — temporary by design
FAILURE_COUNT_TTL = 900  # consecutive-failure counters expire on their own


@dataclass
class RateLimitDecision:
    """Outcome of a pre-login rate-limit check."""

    allowed: bool
    retry_after_seconds: int = 0
    reason: str = ""


class _Backend(Protocol):
    async def count_in_window(self, key: str, now: float, window: int) -> int: ...
    async def add_to_window(self, key: str, now: float, window: int) -> None: ...
    async def get_lockout(self, key: str, now: float) -> float: ...
    async def set_lockout(self, key: str, until: float, now: float) -> None: ...
    async def get_failures(self, key: str) -> int: ...
    async def incr_failures(self, key: str) -> int: ...
    async def reset_failures(self, key: str) -> None: ...


class _RedisBackend:
    """Sliding window via sorted sets; lockout/failure counters via TTL keys."""

    def __init__(self, redis: Any) -> None:  # noqa: ANN401 — redis.asyncio.Redis
        self._redis = redis

    async def count_in_window(self, key: str, now: float, window: int) -> int:
        await self._redis.zremrangebyscore(key, 0, now - window)
        return int(await self._redis.zcard(key))

    async def add_to_window(self, key: str, now: float, window: int) -> None:
        await self._redis.zadd(key, {f"{now!r}:{id(object())}": now})
        await self._redis.expire(key, window * 2)

    async def get_lockout(self, key: str, now: float) -> float:
        raw = await self._redis.get(key)
        return float(raw) if raw else 0.0

    async def set_lockout(self, key: str, until: float, now: float) -> None:
        ttl = max(1, int(until - now))
        await self._redis.set(key, until, ex=ttl)

    async def get_failures(self, key: str) -> int:
        raw = await self._redis.get(key)
        return int(raw) if raw else 0

    async def incr_failures(self, key: str) -> int:
        count = int(await self._redis.incr(key))
        await self._redis.expire(key, FAILURE_COUNT_TTL)
        return count

    async def reset_failures(self, key: str) -> None:
        await self._redis.delete(key)


class _MemoryBackend:
    """Per-process fallback when Redis is unavailable."""

    def __init__(self) -> None:
        self._windows: dict[str, list[float]] = {}
        self._lockouts: dict[str, float] = {}
        self._failures: dict[str, tuple[int, float]] = {}  # count, expiry

    async def count_in_window(self, key: str, now: float, window: int) -> int:
        entries = [t for t in self._windows.get(key, []) if t > now - window]
        self._windows[key] = entries
        return len(entries)

    async def add_to_window(self, key: str, now: float, window: int) -> None:
        self._windows.setdefault(key, []).append(now)

    async def get_lockout(self, key: str, now: float) -> float:
        until = self._lockouts.get(key, 0.0)
        if until <= now:
            self._lockouts.pop(key, None)
            return 0.0
        return until

    async def set_lockout(self, key: str, until: float, now: float) -> None:
        self._lockouts[key] = until

    async def get_failures(self, key: str) -> int:
        count, expiry = self._failures.get(key, (0, 0.0))
        if expiry and expiry < time.monotonic():
            self._failures.pop(key, None)
            return 0
        return count

    async def incr_failures(self, key: str) -> int:
        count = await self.get_failures(key) + 1
        self._failures[key] = (count, time.monotonic() + FAILURE_COUNT_TTL)
        return count

    async def reset_failures(self, key: str) -> None:
        self._failures.pop(key, None)


@dataclass
class LoginRateLimiter:
    """Rate limiter for the login endpoint.

    One instance per app (stateless apart from its backends); pass the
    shared Redis client when available.
    """

    redis: Any = None  # redis.asyncio.Redis | None
    window_seconds: int = WINDOW_SECONDS
    ip_max_attempts: int = IP_MAX_ATTEMPTS
    account_max_failures: int = ACCOUNT_MAX_FAILURES
    lockout_base_seconds: int = LOCKOUT_BASE_SECONDS
    lockout_max_seconds: int = LOCKOUT_MAX_SECONDS
    _memory: _MemoryBackend = field(default_factory=_MemoryBackend)

    def _backends(self) -> list[_Backend]:
        """Redis first when configured; memory fallback is always available."""
        backends: list[_Backend] = []
        if self.redis is not None:
            backends.append(_RedisBackend(self.redis))
        backends.append(self._memory)
        return backends

    async def _call(self, method: str, *args: Any) -> Any:  # noqa: ANN401 — dispatch helper
        """Invoke a backend method, degrading to memory on Redis errors."""
        backends = self._backends()
        for i, backend in enumerate(backends):
            try:
                return await getattr(backend, method)(*args)
            except Exception as exc:
                if i == len(backends) - 1:
                    raise
                log.warning(
                    "rate_limit_backend_degraded",
                    backend=type(backend).__name__,
                    method=method,
                    error=str(exc),
                )
        return None  # pragma: no cover

    # ── Public API ────────────────────────────────────────────────────────────

    async def check(self, *, ip: str | None, email: str) -> RateLimitDecision:
        """Pre-login check. Call before verifying credentials."""
        now = time.time()
        email_key = f"rl:login:lock:{email.lower()}"

        lockout_until = await self._call("get_lockout", email_key, now)
        if lockout_until > now:
            return RateLimitDecision(
                allowed=False,
                retry_after_seconds=max(1, int(lockout_until - now)),
                reason="account_locked",
            )

        if ip:
            ip_key = f"rl:login:ip:{ip}"
            attempts = await self._call("count_in_window", ip_key, now, self.window_seconds)
            if attempts >= self.ip_max_attempts:
                return RateLimitDecision(
                    allowed=False,
                    retry_after_seconds=self.window_seconds,
                    reason="ip_rate_limited",
                )
            await self._call("add_to_window", ip_key, now, self.window_seconds)

        return RateLimitDecision(allowed=True)

    async def record_failure(self, *, email: str) -> None:
        """Record a failed credential check; applies exponential lockout."""
        now = time.time()
        fail_key = f"rl:login:fail:{email.lower()}"
        lock_key = f"rl:login:lock:{email.lower()}"

        failures = await self._call("incr_failures", fail_key)
        if failures >= self.account_max_failures:
            excess = failures - self.account_max_failures
            duration = min(
                self.lockout_base_seconds * (2**excess),
                self.lockout_max_seconds,
            )
            await self._call("set_lockout", lock_key, now + duration, now)
            log.warning(
                "login_account_locked",
                email=email,
                failures=failures,
                lockout_seconds=duration,
            )

    async def record_success(self, *, email: str) -> None:
        """Reset the consecutive-failure counter after a successful login."""
        await self._call("reset_failures", f"rl:login:fail:{email.lower()}")


# ── Email-sending rate limiting (EP-24.4) ───────────────────────────────────
#
# Protects POST /v1/auth/resend-verification and POST /v1/auth/forgot-password
# (and .../request-password-reset, its pre-EP-24.4 alias) against being used
# to spam a mailbox or exhaust Resend's send quota. Deliberately reuses
# _RedisBackend/_MemoryBackend (the storage layer above is already fully
# generic — it has no login-specific logic) rather than a second sliding-
# window implementation; only the policy (one sliding window, no lockout)
# differs from LoginRateLimiter, which is why this is a distinct, smaller
# class rather than a parameterization of LoginRateLimiter itself.

EMAIL_RATE_LIMIT_WINDOW_SECONDS = 300  # 5 minutes
EMAIL_RATE_LIMIT_MAX_ATTEMPTS = 3


@dataclass
class EmailRateLimiter:
    """Sliding-window rate limiter for verification/password-reset email sends.

    One instance shared across requests (same construction pattern as
    ``LoginRateLimiter``) — pass the shared Redis client when available.
    """

    redis: Any = None  # redis.asyncio.Redis | None
    window_seconds: int = EMAIL_RATE_LIMIT_WINDOW_SECONDS
    max_attempts: int = EMAIL_RATE_LIMIT_MAX_ATTEMPTS
    _memory: _MemoryBackend = field(default_factory=_MemoryBackend)

    def _backends(self) -> list[_Backend]:
        backends: list[_Backend] = []
        if self.redis is not None:
            backends.append(_RedisBackend(self.redis))
        backends.append(self._memory)
        return backends

    async def _call(self, method: str, *args: Any) -> Any:  # noqa: ANN401 — dispatch helper
        backends = self._backends()
        for i, backend in enumerate(backends):
            try:
                return await getattr(backend, method)(*args)
            except Exception as exc:
                if i == len(backends) - 1:
                    raise
                log.warning(
                    "rate_limit_backend_degraded",
                    backend=type(backend).__name__,
                    method=method,
                    error=str(exc),
                )
        return None  # pragma: no cover

    async def check_and_record(self, *, scope: str, key: str) -> RateLimitDecision:
        """Check whether ``key`` (an email address, lowercased by the
        caller) is within its send quota for ``scope`` (e.g. ``"verify"``,
        ``"reset"`` — keeps the two email types' quotas independent), and
        record this attempt if so. Always records the attempt when
        allowed, so N calls in a window always exhausts the quota — there
        is no separate "peek without consuming" mode, matching how the
        caller always intends to actually send on an allowed check."""
        now = time.time()
        window_key = f"rl:email:{scope}:{key}"
        attempts = await self._call("count_in_window", window_key, now, self.window_seconds)
        if attempts >= self.max_attempts:
            return RateLimitDecision(
                allowed=False,
                retry_after_seconds=self.window_seconds,
                reason="email_rate_limited",
            )
        await self._call("add_to_window", window_key, now, self.window_seconds)
        return RateLimitDecision(allowed=True)
