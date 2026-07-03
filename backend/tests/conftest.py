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
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.config.settings import Settings
from app.core.container import AppContainer
from app.core.logging import configure_logging
from app.db.mixins import uuid7
from app.main import create_app
from app.models.membership import Membership, MembershipRole
from app.models.organization import Organization, OrganizationStatus
from app.models.organization_api_key import OrganizationApiKey
from app.models.project import Project, ProjectEnvironment
from app.models.provider_connection import ProviderConnection, ProviderType
from app.models.usage_record import UsageRecord, UsageRecordStatus
from app.models.user import User, UserStatus
from app.realtime.connection_manager import ConnectionManager
from app.realtime.event_bus import EventBus
from app.realtime.rate_limit import ConnectionRateLimiter

# ─── Logging ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True, scope="session")
def _configure_test_logging() -> None:
    """
    Configure structlog once for the whole test session.

    The `app` fixture deliberately skips the real application lifespan (no
    network I/O), so `configure_from_settings` — which would normally set
    this up on startup — never runs. Without it, structlog falls back to its
    library default: a rich-backed ConsoleRenderer with show_locals=True.
    Tests routinely let exceptions propagate through unittest.mock objects
    (e.g. an endpoint test with an intentionally-invalid mock), and rich's
    recursive pretty-printer can take pathologically long — even hang for
    minutes — trying to render a MagicMock's locals (every attribute access
    on a MagicMock returns another MagicMock). configure_logging("testing")
    uses a plain-text exception formatter instead, which is instant.
    """
    configure_logging(environment="testing")


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
    event_bus = EventBus(mock_redis)

    container = AppContainer(
        settings=settings,
        engine=mock_engine,
        session_factory=mock_session_factory,
        redis=mock_redis,
        event_bus=event_bus,
        # Dispatch loop deliberately not started here — most tests don't need
        # it and starting it requires a running event loop at fixture time.
        connection_manager=ConnectionManager(event_bus),
        realtime_rate_limiter=ConnectionRateLimiter(redis=mock_redis),
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


@pytest.fixture
async def auth_client(app: FastAPI) -> AsyncGenerator[AsyncClient]:
    """
    Authenticated test client: bypasses JWT validation and the org-membership
    guard so endpoint behavior can be tested in isolation. Authorization
    semantics themselves are covered in tests/test_authz.py.
    """
    from unittest.mock import AsyncMock, MagicMock

    from app.api.deps import get_db
    from app.api.v1.usage import get_body_org_membership
    from app.auth.dependencies import get_current_user, get_query_org_membership
    from app.models.membership import Membership
    from app.models.user import User

    async def _mock_user() -> User:
        user = MagicMock(spec=User)
        user.email = "testuser@example.com"
        return user

    async def _mock_membership() -> Membership:
        return MagicMock(spec=Membership)

    async def _mock_db() -> AsyncGenerator[AsyncMock]:
        yield AsyncMock()

    app.dependency_overrides[get_current_user] = _mock_user
    app.dependency_overrides[get_query_org_membership] = _mock_membership
    app.dependency_overrides[get_body_org_membership] = _mock_membership
    app.dependency_overrides[get_db] = _mock_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_query_org_membership, None)
        app.dependency_overrides.pop(get_body_org_membership, None)
        app.dependency_overrides.pop(get_db, None)


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


def make_api_key(
    *,
    org_id: uuid.UUID | None = None,
    name: str = "CI pipeline",
    key_prefix: str = "costorah_live_ab12cd34",
    key_hash: str = "a" * 64,
    permissions: list[str] | None = None,
    created_by: uuid.UUID | None = None,
) -> OrganizationApiKey:
    """Return a transient OrganizationApiKey instance."""
    obj = OrganizationApiKey()
    obj.id = uuid7()
    obj.organization_id = org_id or uuid7()
    obj.name = name
    obj.description = None
    obj.key_prefix = key_prefix
    obj.key_hash = key_hash
    obj.permissions = permissions if permissions is not None else []
    obj.created_by = created_by
    obj.last_used_at = None
    obj.expires_at = None
    obj.created_at = datetime.now(UTC)
    obj.updated_at = obj.created_at
    return obj


def make_usage_record(
    *,
    org_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    api_key_id: uuid.UUID | None = None,
    provider: str = "openai",
    model: str = "gpt-4.1",
    request_id: str = "req_123456",
    status: UsageRecordStatus = UsageRecordStatus.SUCCESS,
    input_tokens: int = 1200,
    output_tokens: int = 320,
    cached_tokens: int | None = 0,
    total_tokens: int = 1520,
    cost: Decimal | None = None,
    currency: str = "USD",
    latency_ms: int | None = 742,
    region: str | None = None,
    metadata: dict[str, object] | None = None,
    request_timestamp: datetime | None = None,
) -> UsageRecord:
    """Return a transient UsageRecord instance."""
    obj = UsageRecord()
    obj.id = uuid7()
    obj.organization_id = org_id or uuid7()
    obj.project_id = project_id
    obj.api_key_id = api_key_id
    obj.provider = provider
    obj.model = model
    obj.request_id = request_id
    obj.status = status
    obj.input_tokens = input_tokens
    obj.output_tokens = output_tokens
    obj.cached_tokens = cached_tokens
    obj.total_tokens = total_tokens
    obj.cost = cost if cost is not None else Decimal("0.0812")
    obj.currency = currency
    obj.latency_ms = latency_ms
    obj.region = region
    obj.usage_metadata = metadata if metadata is not None else {}
    now = datetime.now(UTC)
    obj.ingested_at = now
    obj.request_timestamp = request_timestamp or now
    obj.created_at = now
    obj.updated_at = now
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
