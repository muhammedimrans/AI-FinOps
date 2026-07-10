"""Security headers middleware tests."""

from __future__ import annotations

from typing import Any

import pytest

from app.config.settings import Settings
from app.main import create_app


class TestSecurityHeaders:
    @pytest.mark.asyncio
    async def test_standard_headers_present(self, client: Any) -> None:
        resp = await client.get("/v1/health")
        assert resp.headers["x-content-type-options"] == "nosniff"
        assert resp.headers["x-frame-options"] == "DENY"
        assert resp.headers["referrer-policy"] == "no-referrer"
        assert "default-src 'none'" in resp.headers["content-security-policy"]
        assert "frame-ancestors 'none'" in resp.headers["content-security-policy"]
        assert "permissions-policy" in resp.headers

    @pytest.mark.asyncio
    async def test_no_hsts_outside_production(self, client: Any) -> None:
        resp = await client.get("/v1/health")
        assert "strict-transport-security" not in resp.headers

    def test_hsts_enabled_in_production_app(self) -> None:
        settings = Settings(
            app_secret_key="a" * 32,
            jwt_secret="j" * 32,
            app_env="production",
            resend_api_key="re_test_key",
            email_from="noreply@costorah.com",
        )
        app = create_app(settings)
        # Verify the middleware was registered with hsts=True
        added = [m for m in app.user_middleware if m.cls.__name__ == "SecurityHeadersMiddleware"]
        assert added, "SecurityHeadersMiddleware not registered"
        assert added[0].kwargs.get("hsts") is True

    @pytest.mark.asyncio
    async def test_auth_responses_not_cached(self, client: Any) -> None:
        # Unauthenticated logout returns 401 before touching the DB — the
        # response still flows through the middleware like any auth response.
        resp = await client.post("/v1/auth/logout")
        assert resp.headers.get("cache-control") == "no-store"

    @pytest.mark.asyncio
    async def test_data_endpoints_not_forced_no_store(self, client: Any) -> None:
        resp = await client.get("/v1/health")
        assert resp.headers.get("cache-control") != "no-store"
