"""
Test fixtures for the AI FinOps backend test suite.

All tests run without live infrastructure services by default.
The AppContainer is replaced with mocks so tests remain fast and hermetic.
Tests requiring live Postgres/Redis are marked @pytest.mark.integration
and are skipped in the default run.

Model factory helpers (_make_org, _make_project, etc.) are defined here so
all test files share a single canonical source of truth for transient ORM
instances (TD-018).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.config.settings import Settings
from app.core.container import AppContainer
from app.db.mixins import uuid7
from app.main import create_app
from app.models.membership import Membership, MembershipRole
from app.models.organization import Organization, OrganizationStatus
from app.models.project import Project, ProjectEnvironment
from app.models.provider_connection import ProviderConnection, ProviderType
from app.models.user import User, UserStatus

# ─── Environment isolation ────────────────────────────────────────────────────


@pytest.fixture(autouse=True, scope="session")
def _isolate_env() -> None:
    """
    Prevent environment variables (local .env or CI workflow) from leaking
    into unit tests.

    - DATABASE_URL / JWT_SECRET: set to empty so tests use computed defaults
    - APP_ENV / APP_SECRET_KEY: removed entirely so Settings uses its own
      defaults (these cannot be set to empty — pydantic would reject them)
    """
    overrides = {"DATABASE_URL": "", "JWT_SECRET": ""}
    originals_override = {k: os.environ.get(k) for k in overrides}
    os.environ.update(overrides)

    # Pop keys that can't be set to empty (strict Literal / min_length types)
    pop_keys = ["APP_ENV", "APP_SECRET_KEY"]
    originals_pop = {k: os.environ.pop(k, None) for k in pop_keys}

    yield

    for k, v in originals_override.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    for k, v in originals_pop.items():
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
        jwt_secret="test-jwt-secret-for-unit-tests-only!!",
    )


# ─── Mock container ───────────────────────────────────────────────────────────


def _make_mock_container(
    settings: Settings, db_healthy: bool = True, redis_healthy: bool = True
) -> AppContainer:
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
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient]:
    """
    Async HTTP test client backed by the ASGI app.
    Skips the lifespan (container is pre-injected via app.state).
    """
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


# ─── Model Factories ──────────────────────────────────────────────────────────
# Canonical transient ORM instances for use across all test files.
# These do NOT hit the database; they are plain Python objects.


def make_user(
    *,
    email: str = "alice@example.com",
    username: str | None = "alice",
    display_name: str = "Alice",
    status: UserStatus = UserStatus.ACTIVE,
    email_verified: bool = False,
    password_hash: str | None = None,
) -> User:
    """Return a transient User instance with a generated UUIDv7 id."""
    obj = User()
    obj.id = uuid7()
    obj.email = email
    obj.username = username
    obj.display_name = display_name
    obj.status = status
    obj.email_verified = email_verified
    obj.password_hash = password_hash
    return obj


def make_org(
    *,
    name: str = "Acme Corp",
    slug: str = "acme",
    status: OrganizationStatus = OrganizationStatus.ACTIVE,
) -> Organization:
    """Return a transient Organization instance with a generated UUIDv7 id."""
    obj = Organization()
    obj.id = uuid7()
    obj.name = name
    obj.slug = slug
    obj.status = status
    return obj


def make_project(
    *,
    org_id: uuid.UUID | None = None,
    name: str = "Main Project",
    environment: ProjectEnvironment = ProjectEnvironment.PRODUCTION,
) -> Project:
    """Return a transient Project instance."""
    obj = Project()
    obj.id = uuid7()
    obj.organization_id = org_id or uuid7()
    obj.name = name
    obj.environment = environment
    return obj


def make_membership(
    *,
    org_id: uuid.UUID | None = None,
    user_email: str = "alice@example.com",
    role: MembershipRole = MembershipRole.MEMBER,
) -> Membership:
    """Return a transient Membership instance."""
    obj = Membership()
    obj.id = uuid7()
    obj.organization_id = org_id or uuid7()
    obj.user_email = user_email
    obj.role = role
    return obj


def make_connection(
    *,
    org_id: uuid.UUID | None = None,
    provider_type: ProviderType = ProviderType.OPENAI,
) -> ProviderConnection:
    """Return a transient ProviderConnection instance."""
    obj = ProviderConnection()
    obj.id = uuid7()
    obj.organization_id = org_id or uuid7()
    obj.provider_name = "openai"
    obj.display_name = "OpenAI"
    obj.provider_type = provider_type
    obj.is_active = True
    obj.configuration = {}
    return obj


# ─── Helpers ──────────────────────────────────────────────────────────────────


def assert_response_shape(body: dict[str, Any], *, ok: bool) -> None:
    """Assert the standard API envelope shape."""
    assert "ok" in body or "status" in body  # health endpoints use status, not ok
