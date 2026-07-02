"""Login rate limiting tests — sliding window, lockout, backoff, fallback."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.auth.rate_limit import LoginRateLimiter, RateLimitDecision

_EMAIL = "victim@example.com"
_IP = "203.0.113.7"


def _limiter(**kwargs: Any) -> LoginRateLimiter:
    """Memory-backed limiter with small thresholds for fast tests."""
    defaults: dict[str, Any] = {
        "redis": None,
        "window_seconds": 60,
        "ip_max_attempts": 3,
        "account_max_failures": 2,
        "lockout_base_seconds": 30,
        "lockout_max_seconds": 900,
    }
    defaults.update(kwargs)
    return LoginRateLimiter(**defaults)


class TestIPWindow:
    @pytest.mark.asyncio
    async def test_attempts_under_limit_allowed(self) -> None:
        limiter = _limiter()
        for _ in range(3):
            decision = await limiter.check(ip=_IP, email=_EMAIL)
            assert decision.allowed

    @pytest.mark.asyncio
    async def test_attempts_over_limit_blocked(self) -> None:
        limiter = _limiter()
        for _ in range(3):
            await limiter.check(ip=_IP, email=_EMAIL)
        decision = await limiter.check(ip=_IP, email=_EMAIL)
        assert not decision.allowed
        assert decision.reason == "ip_rate_limited"
        assert decision.retry_after_seconds > 0

    @pytest.mark.asyncio
    async def test_different_ips_tracked_separately(self) -> None:
        limiter = _limiter()
        for _ in range(3):
            await limiter.check(ip=_IP, email=_EMAIL)
        decision = await limiter.check(ip="198.51.100.1", email=_EMAIL)
        assert decision.allowed

    @pytest.mark.asyncio
    async def test_missing_ip_does_not_crash(self) -> None:
        limiter = _limiter()
        decision = await limiter.check(ip=None, email=_EMAIL)
        assert decision.allowed


class TestAccountLockout:
    @pytest.mark.asyncio
    async def test_lockout_after_max_failures(self) -> None:
        limiter = _limiter()
        await limiter.record_failure(email=_EMAIL)
        await limiter.record_failure(email=_EMAIL)  # hits account_max_failures=2
        decision = await limiter.check(ip=None, email=_EMAIL)
        assert not decision.allowed
        assert decision.reason == "account_locked"
        assert 0 < decision.retry_after_seconds <= 30

    @pytest.mark.asyncio
    async def test_lockout_is_per_account(self) -> None:
        limiter = _limiter()
        await limiter.record_failure(email=_EMAIL)
        await limiter.record_failure(email=_EMAIL)
        decision = await limiter.check(ip=None, email="other@example.com")
        assert decision.allowed

    @pytest.mark.asyncio
    async def test_email_case_insensitive(self) -> None:
        limiter = _limiter()
        await limiter.record_failure(email=_EMAIL.upper())
        await limiter.record_failure(email=_EMAIL)
        decision = await limiter.check(ip=None, email=_EMAIL.title())
        assert not decision.allowed

    @pytest.mark.asyncio
    async def test_exponential_backoff_capped(self) -> None:
        limiter = _limiter(lockout_base_seconds=30, lockout_max_seconds=120)
        for _ in range(20):
            await limiter.record_failure(email=_EMAIL)
        decision = await limiter.check(ip=None, email=_EMAIL)
        assert not decision.allowed
        # capped — never permanent, never beyond lockout_max_seconds
        assert decision.retry_after_seconds <= 120

    @pytest.mark.asyncio
    async def test_success_resets_failures(self) -> None:
        limiter = _limiter()
        await limiter.record_failure(email=_EMAIL)
        await limiter.record_success(email=_EMAIL)
        await limiter.record_failure(email=_EMAIL)
        # only 1 consecutive failure since reset — below the threshold of 2
        decision = await limiter.check(ip=None, email=_EMAIL)
        assert decision.allowed

    @pytest.mark.asyncio
    async def test_lockout_expires(self) -> None:
        limiter = _limiter(lockout_base_seconds=1)
        await limiter.record_failure(email=_EMAIL)
        await limiter.record_failure(email=_EMAIL)
        assert not (await limiter.check(ip=None, email=_EMAIL)).allowed
        with patch("app.auth.rate_limit.time.time", return_value=__import__("time").time() + 5):
            decision = await limiter.check(ip=None, email=_EMAIL)
        assert decision.allowed


class TestRedisFallback:
    @pytest.mark.asyncio
    async def test_redis_failure_degrades_to_memory(self) -> None:
        """A broken Redis must not fail open or take login down."""
        broken_redis = MagicMock()
        broken_redis.get = AsyncMock(side_effect=ConnectionError("redis down"))
        broken_redis.zremrangebyscore = AsyncMock(side_effect=ConnectionError("redis down"))
        limiter = _limiter(redis=broken_redis)

        # still enforces via memory backend
        for _ in range(3):
            assert (await limiter.check(ip=_IP, email=_EMAIL)).allowed
        decision = await limiter.check(ip=_IP, email=_EMAIL)
        assert not decision.allowed


class TestLoginEndpointIntegration:
    @pytest.mark.asyncio
    async def test_login_returns_429_when_limited(self, app: Any, client: Any) -> None:
        """End-to-end: the endpoint returns 429 + Retry-After once limited."""
        limiter = _limiter(ip_max_attempts=0)  # block immediately
        app.state.login_rate_limiter = limiter
        resp = await client.post(
            "/v1/auth/login",
            json={"email": _EMAIL, "password": "wrong-password-123"},
        )
        assert resp.status_code == 429
        assert "retry-after" in {k.lower() for k in resp.headers}

    @pytest.mark.asyncio
    async def test_locked_account_returns_429(self, app: Any, client: Any) -> None:
        limiter = _limiter(account_max_failures=1)
        await limiter.record_failure(email=_EMAIL)
        app.state.login_rate_limiter = limiter
        resp = await client.post(
            "/v1/auth/login",
            json={"email": _EMAIL, "password": "wrong-password-123"},
        )
        assert resp.status_code == 429

    def test_decision_defaults(self) -> None:
        decision = RateLimitDecision(allowed=True)
        assert decision.retry_after_seconds == 0
        assert decision.reason == ""
