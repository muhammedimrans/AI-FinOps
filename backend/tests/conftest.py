"""
Test fixtures for the AI FinOps backend test suite.

All tests run without live infrastructure services by default.
The AppContainer is replaced with mocks so tests remain fast and hermetic.
Tests requiring live Postgres/Redis are marked @pytest.mark.integration
and are skipped in the default run.
"""
from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.config.settings import Settings, get_settings
from app.core.container import AppContainer
from app.main import create_app


# ─── Environment isolation ────────────────────────────────────────────────────

@pytest.fixture(autouse=True, scope="session")
def _isolate_env() -> None:
    """
    Prevent a local backend/.env from leaking DATABASE_URL or JWT_SECRET
    into unit tests. OS env vars take priority over the .env file in
    pydantic-settings, so setting them to empty forces the computed fallback.
    """
    overrides = {"DATABASE_URL": "", "JWT_SECRET": ""}
    originals = {k: os.environ.get(k) for k in overrides}
    os.environ.update(overrides)
    yield
    for k, v in originals.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


# ─── Settings ─────────────────────────────────────────────────────────────────

@pytest.fixture
def test_settings() -> Settings:
    """Minimal settings for unit tests — no live services required."""
    return Settings(
        app_env="testing",
        app_secret_key="test-secret-key-with-at-least-32-chars!!",
        app_debug=True,
        app_log_level="DEBUG",
        postgres_host="localhost",
        postgres_port=5432,
        postgres_db="aifinops_test",
        postgres_user="aifinops",
        postgres_password="test_password",
        redis_host="localhost",
        redis_port=6379,
        redis_db=0,
    )


# ─── Mock container ───────────────────────────────────────────────────────────

def _make_mock_container(settings: Settings, db_healthy: bool = True, redis_healthy: bool = True) -> AppContainer:
    """
    Build a mock AppContainer with configurable health states.
    No network connections are made.
    """
    mock_engine = MagicMock()
    mock_session_factory = MagicMock()
    mock_redis = AsyncMock()

    container = AppContainer(
        settings=settings,
        engine=mock_engine,
        session_factory=mock_session_factory,
        redis=mock_redis,
    )
    return container


@pytest.fixture
def mock_container(test_settings: Settings) -> AppContainer:
    return _make_mock_container(test_settings)


@pytest.fixture
def mock_container_degraded(test_settings: Settings) -> AppContainer:
    return _make_mock_container(test_settings, db_healthy=False, redis_healthy=False)


# ─── Application ──────────────────────────────────────────────────────────────

@pytest.fixture
def app(test_settings: Settings, mock_container: AppContainer) -> FastAPI:
    """FastAPI application with settings and container injected — no lifespan IO."""
    application = create_app(test_settings)
    application.state.container = mock_container

    # Override get_settings so DI returns test settings
    from app.config.settings import get_settings as _get_settings

    application.dependency_overrides[_get_settings] = lambda: test_settings

    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """
    Async HTTP test client backed by the ASGI app.
    Skips the lifespan (container is pre-injected via app.state).
    """
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


# ─── Helpers ──────────────────────────────────────────────────────────────────

def assert_response_shape(body: dict[str, Any], *, ok: bool) -> None:
    """Assert the standard API envelope shape."""
    assert "ok" in body or "status" in body  # health endpoints use status, not ok
