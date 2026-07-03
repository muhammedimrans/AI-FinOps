"""EP-19.1 — Real-Time Telemetry Platform Foundation tests.

Covers: event model, Redis-backed event bus, connection manager
(dispatch/backpressure/organization isolation), auth reuse (JWT + API Key
paths), per-IP rate limiting, and the WebSocket/SSE gateway endpoints.

All unit tests run without live infrastructure (Redis/Postgres mocked),
matching this suite's existing convention (see tests/conftest.py). A
handful of integration-style tests exercise the real WebSocket/SSE ASGI
protocol via Starlette's TestClient/httpx, with authentication mocked at
the `authenticate_realtime_connection` boundary — the same boundary the
route handlers themselves call through, so this still proves the gateway
wiring (rate limiting, registration, dispatch, heartbeat, teardown) is
correct end to end without needing a live Postgres/Redis for CI.
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from jwt.exceptions import ExpiredSignatureError
from starlette.testclient import TestClient

from app.auth.exceptions import (
    ApiKeyExpiredError,
    InvalidApiKeyError,
    OrganizationSuspendedError,
)
from app.auth.rbac import Permission
from app.auth.tokens import create_access_token
from app.config.settings import Settings
from app.core.container import AppContainer
from app.main import create_app
from app.models.membership import MembershipRole
from app.models.organization import OrganizationStatus
from app.models.user import UserStatus
from app.realtime.auth import (
    PrincipalKind,
    RealtimeAuthError,
    RealtimeAuthErrorReason,
    authenticate_realtime_connection,
    extract_token,
)
from app.realtime.connection_manager import ConnectionKind, ConnectionManager
from app.realtime.event_bus import EventBus
from app.realtime.events import (
    CURRENT_EVENT_VERSION,
    EventType,
    RealtimeEvent,
    org_channel,
    org_id_from_channel,
)
from app.realtime.rate_limit import ConnectionRateLimiter
from app.services.api_key_auth_service import ApiKeyAuthContext
from tests.conftest import make_membership, make_org, make_user


def _settings() -> Settings:
    return Settings(
        app_env="testing",
        app_secret_key="test-secret-key-with-at-least-32-chars!!",
        postgres_host="localhost",
        postgres_db="aifinops_test",
        postgres_user="aifinops",
        postgres_password="test_password",
        redis_host="localhost",
        jwt_secret="test-jwt-secret-for-unit-tests-only!!",
    )


def _event(organization_id: uuid.UUID | None = None, **kwargs: object) -> RealtimeEvent:
    defaults: dict[str, object] = {
        "organization_id": organization_id or uuid.uuid4(),
        "type": EventType.USAGE_CREATED,
        "payload": {"provider": "openai"},
    }
    defaults.update(kwargs)
    return RealtimeEvent(**defaults)  # type: ignore[arg-type]


# ─── Event model ──────────────────────────────────────────────────────────────


class TestEventModel:
    def test_envelope_has_all_ticket_fields(self) -> None:
        org_id = uuid.uuid4()
        event = RealtimeEvent(
            organization_id=org_id,
            type=EventType.USAGE_CREATED,
            payload={"foo": "bar"},
            trace_id="req_123",
            correlation_id="corr_456",
        )
        assert event.organization_id == org_id
        assert event.type == EventType.USAGE_CREATED
        assert event.version == CURRENT_EVENT_VERSION
        assert event.payload == {"foo": "bar"}
        assert event.trace_id == "req_123"
        assert event.correlation_id == "corr_456"
        assert isinstance(event.event_id, uuid.UUID)
        assert event.timestamp.tzinfo is not None

    def test_all_twelve_event_types_defined(self) -> None:
        expected = {
            "usage.created",
            "usage.updated",
            "budget.threshold_reached",
            "budget.exceeded",
            "provider.error",
            "provider.recovery",
            "api_key.created",
            "api_key.deleted",
            "sdk.connected",
            "sdk.disconnected",
            "organization.updated",
            "notification.created",
        }
        assert {member.value for member in EventType} == expected

    def test_channel_round_trips_through_org_id_from_channel(self) -> None:
        org_id = uuid.uuid4()
        channel = org_channel(org_id)
        assert channel == f"realtime:org:{org_id}"
        assert org_id_from_channel(channel) == org_id

    def test_org_id_from_channel_never_raises_on_garbage(self) -> None:
        assert org_id_from_channel("not-a-channel") is None
        assert org_id_from_channel("realtime:org:not-a-uuid") is None
        assert org_id_from_channel("") is None

    def test_event_serializes_round_trip(self) -> None:
        event = _event()
        parsed = RealtimeEvent.model_validate_json(event.model_dump_json())
        assert parsed == event


# ─── Event bus ────────────────────────────────────────────────────────────────


class TestEventBus:
    async def test_publish_calls_redis_pipeline(self) -> None:
        redis = AsyncMock()
        pipe = AsyncMock()
        redis.pipeline = MagicMock(return_value=pipe)
        bus = EventBus(redis)
        event = _event()

        await bus.publish(event)

        pipe.publish.assert_called_once()
        pipe.rpush.assert_called_once()
        pipe.ltrim.assert_called_once()
        pipe.expire.assert_called_once()
        pipe.execute.assert_awaited_once()

    async def test_publish_never_raises_on_redis_error(self) -> None:
        redis = AsyncMock()
        redis.pipeline.side_effect = ConnectionError("redis down")
        bus = EventBus(redis)
        await bus.publish(_event())  # must not raise

    async def test_replay_since_returns_events_after_last_seen(self) -> None:
        org_id = uuid.uuid4()
        e1, e2, e3 = _event(org_id), _event(org_id), _event(org_id)
        redis = AsyncMock()
        redis.lrange.return_value = [
            e.model_dump_json().encode() for e in (e1, e2, e3)
        ]
        bus = EventBus(redis)

        result = await bus.replay_since(org_id, e1.event_id)
        assert [e.event_id for e in result] == [e2.event_id, e3.event_id]

    async def test_replay_since_none_returns_everything_buffered(self) -> None:
        org_id = uuid.uuid4()
        e1, e2 = _event(org_id), _event(org_id)
        redis = AsyncMock()
        redis.lrange.return_value = [e.model_dump_json().encode() for e in (e1, e2)]
        bus = EventBus(redis)

        result = await bus.replay_since(org_id, None)
        assert [e.event_id for e in result] == [e1.event_id, e2.event_id]

    async def test_replay_since_unknown_id_returns_everything(self) -> None:
        org_id = uuid.uuid4()
        e1 = _event(org_id)
        redis = AsyncMock()
        redis.lrange.return_value = [e1.model_dump_json().encode()]
        bus = EventBus(redis)

        result = await bus.replay_since(org_id, uuid.uuid4())
        assert [e.event_id for e in result] == [e1.event_id]

    async def test_replay_since_never_raises_on_redis_error(self) -> None:
        redis = AsyncMock()
        redis.lrange.side_effect = ConnectionError("redis down")
        bus = EventBus(redis)
        result = await bus.replay_since(uuid.uuid4(), None)
        assert result == []

    async def test_replay_since_skips_malformed_entries(self) -> None:
        org_id = uuid.uuid4()
        good = _event(org_id)
        redis = AsyncMock()
        redis.lrange.return_value = [b"not json", good.model_dump_json().encode()]
        bus = EventBus(redis)
        result = await bus.replay_since(org_id, None)
        assert [e.event_id for e in result] == [good.event_id]


# ─── Connection manager ───────────────────────────────────────────────────────


class TestConnectionManager:
    def _manager(self) -> ConnectionManager:
        return ConnectionManager(EventBus(AsyncMock()))

    def test_register_and_unregister_tracks_counts(self) -> None:
        mgr = self._manager()
        org_id = uuid.uuid4()
        info = mgr.register(
            organization_id=org_id,
            kind=ConnectionKind.WEBSOCKET,
            principal_kind=PrincipalKind.USER,
            principal_id=uuid.uuid4(),
        )
        assert mgr.connection_count() == 1
        assert mgr.connection_count(org_id) == 1
        assert mgr.connections_for_org(org_id) == [info]

        mgr.unregister(info.connection_id)
        assert mgr.connection_count() == 0
        assert mgr.connection_count(org_id) == 0

    def test_unregister_unknown_connection_is_a_no_op(self) -> None:
        mgr = self._manager()
        assert mgr.unregister("does-not-exist") is None

    def test_dispatch_delivers_only_to_matching_organization(self) -> None:
        """Organization isolation: Tenant A must never receive Tenant B's events."""
        mgr = self._manager()
        org_a, org_b = uuid.uuid4(), uuid.uuid4()
        conn_a = mgr.register(
            organization_id=org_a,
            kind=ConnectionKind.WEBSOCKET,
            principal_kind=PrincipalKind.USER,
            principal_id=uuid.uuid4(),
        )
        conn_b = mgr.register(
            organization_id=org_b,
            kind=ConnectionKind.WEBSOCKET,
            principal_kind=PrincipalKind.USER,
            principal_id=uuid.uuid4(),
        )

        event = _event(org_a)
        mgr.dispatch(org_a, event)

        assert conn_a.queue.get_nowait() is event
        assert conn_b.queue.empty()

    def test_dispatch_fans_out_to_multiple_connections_same_org(self) -> None:
        """Multiple tabs/users/devices/SDKs for one org all receive the event."""
        mgr = self._manager()
        org_id = uuid.uuid4()
        conns = [
            mgr.register(
                organization_id=org_id,
                kind=ConnectionKind.WEBSOCKET,
                principal_kind=PrincipalKind.USER,
                principal_id=uuid.uuid4(),
            )
            for _ in range(4)
        ]
        event = _event(org_id)
        mgr.dispatch(org_id, event)
        for conn in conns:
            assert conn.queue.get_nowait() is event

    def test_dispatch_to_unknown_org_is_a_no_op(self) -> None:
        mgr = self._manager()
        mgr.dispatch(uuid.uuid4(), _event())  # must not raise

    def test_dispatch_drops_on_full_queue_and_calls_on_drop(self) -> None:
        mgr = self._manager()
        org_id = uuid.uuid4()
        info = mgr.register(
            organization_id=org_id,
            kind=ConnectionKind.SSE,
            principal_kind=PrincipalKind.API_KEY,
            principal_id=uuid.uuid4(),
        )
        # Fill the queue past capacity.
        for _ in range(info.queue.maxsize):
            info.queue.put_nowait(_event(org_id))

        dropped: list[object] = []
        mgr.on_drop(lambda dropped_info: dropped.append(dropped_info))
        mgr.dispatch(org_id, _event(org_id))

        assert dropped == [info]

    def test_dispatch_calls_on_dispatch_for_delivered_event(self) -> None:
        mgr = self._manager()
        org_id = uuid.uuid4()
        mgr.register(
            organization_id=org_id,
            kind=ConnectionKind.WEBSOCKET,
            principal_kind=PrincipalKind.USER,
            principal_id=uuid.uuid4(),
        )
        delivered: list[object] = []
        mgr.on_dispatch(lambda info, event: delivered.append(event))
        event = _event(org_id)
        mgr.dispatch(org_id, event)
        assert delivered == [event]

    def test_record_heartbeat_failure_increments_counter(self) -> None:
        mgr = self._manager()
        info = mgr.register(
            organization_id=uuid.uuid4(),
            kind=ConnectionKind.WEBSOCKET,
            principal_kind=PrincipalKind.USER,
            principal_id=uuid.uuid4(),
        )
        mgr.record_heartbeat_failure(info.connection_id)
        mgr.record_heartbeat_failure(info.connection_id)
        assert info.heartbeat_failures == 2

    def test_reconnect_count_is_tracked_on_registration(self) -> None:
        mgr = self._manager()
        info = mgr.register(
            organization_id=uuid.uuid4(),
            kind=ConnectionKind.SSE,
            principal_kind=PrincipalKind.USER,
            principal_id=uuid.uuid4(),
            reconnect_count=3,
        )
        assert info.reconnect_count == 3

    async def test_receive_yields_dispatched_events_until_unregistered(self) -> None:
        mgr = self._manager()
        org_id = uuid.uuid4()
        info = mgr.register(
            organization_id=org_id,
            kind=ConnectionKind.WEBSOCKET,
            principal_kind=PrincipalKind.USER,
            principal_id=uuid.uuid4(),
        )
        event = _event(org_id)
        mgr.dispatch(org_id, event)

        received = []

        async def _consume() -> None:
            async for e in mgr.receive(info.connection_id):
                received.append(e)
                mgr.unregister(info.connection_id)
                return

        await asyncio.wait_for(_consume(), timeout=2)
        assert received == [event]

    async def test_receive_on_unknown_connection_yields_nothing(self) -> None:
        mgr = self._manager()
        results = [e async for e in mgr.receive("does-not-exist")]
        assert results == []

    async def test_start_stop_lifecycle_is_idempotent(self) -> None:
        bus = EventBus(AsyncMock())

        async def _no_events():
            return
            yield  # pragma: no cover

        with patch.object(bus, "subscribe_all_organizations", side_effect=_no_events):
            mgr = ConnectionManager(bus)
            mgr.start()
            mgr.start()  # second call is a no-op, not a second task
            await mgr.stop()
            await mgr.stop()  # stopping twice must not raise


# ─── Rate limiting ────────────────────────────────────────────────────────────


class TestConnectionRateLimiter:
    async def test_missing_ip_always_allowed(self) -> None:
        limiter = ConnectionRateLimiter(redis=None)
        assert await limiter.check(ip=None) is True

    async def test_memory_fallback_allows_under_limit(self) -> None:
        limiter = ConnectionRateLimiter(redis=None, max_attempts=3)
        for _ in range(3):
            assert await limiter.check(ip="203.0.113.5") is True

    async def test_memory_fallback_blocks_over_limit(self) -> None:
        limiter = ConnectionRateLimiter(redis=None, max_attempts=3)
        for _ in range(3):
            await limiter.check(ip="203.0.113.5")
        assert await limiter.check(ip="203.0.113.5") is False

    async def test_different_ips_tracked_separately(self) -> None:
        limiter = ConnectionRateLimiter(redis=None, max_attempts=1)
        assert await limiter.check(ip="203.0.113.5") is True
        assert await limiter.check(ip="198.51.100.9") is True

    async def test_redis_error_degrades_to_memory_fallback(self) -> None:
        redis = AsyncMock()
        redis.pipeline = MagicMock(side_effect=ConnectionError("redis down"))
        limiter = ConnectionRateLimiter(redis=redis, max_attempts=5)
        assert await limiter.check(ip="203.0.113.5") is True

    async def test_redis_backed_check_uses_pipeline_zcard(self) -> None:
        redis = AsyncMock()
        pipe = AsyncMock()
        pipe.execute.return_value = [None, None, 2, None]
        redis.pipeline = MagicMock(return_value=pipe)
        limiter = ConnectionRateLimiter(redis=redis, max_attempts=5)
        assert await limiter.check(ip="203.0.113.5") is True

    async def test_redis_backed_check_blocks_over_limit(self) -> None:
        redis = AsyncMock()
        pipe = AsyncMock()
        pipe.execute.return_value = [None, None, 10, None]
        redis.pipeline = MagicMock(return_value=pipe)
        limiter = ConnectionRateLimiter(redis=redis, max_attempts=5)
        assert await limiter.check(ip="203.0.113.5") is False


# ─── Auth reuse ───────────────────────────────────────────────────────────────


class TestExtractToken:
    def test_bearer_header_wins(self) -> None:
        token = extract_token(authorization_header="Bearer abc123", query_token="xyz")
        assert token == "abc123"

    def test_falls_back_to_query_token(self) -> None:
        token = extract_token(authorization_header=None, query_token="abc123")
        assert token == "abc123"

    def test_missing_both_raises(self) -> None:
        with pytest.raises(RealtimeAuthError) as exc_info:
            extract_token(authorization_header=None, query_token=None)
        assert exc_info.value.reason == RealtimeAuthErrorReason.MISSING_TOKEN

    def test_non_bearer_scheme_falls_back_to_query(self) -> None:
        token = extract_token(authorization_header="Basic abc123", query_token="qtok")
        assert token == "qtok"


class _FakeSessionFactory:
    """Minimal stand-in for `async_sessionmaker` used by authenticate_realtime_connection."""

    def __init__(self, db: AsyncMock) -> None:
        self._db = db

    def __call__(self):
        return self

    async def __aenter__(self) -> AsyncMock:
        return self._db

    async def __aexit__(self, *exc: object) -> None:
        return None


class TestAuthenticateRealtimeConnectionApiKey:
    async def test_valid_api_key_returns_principal(self) -> None:
        org = make_org()
        api_key = MagicMock()
        api_key.id = uuid.uuid4()
        context = ApiKeyAuthContext(api_key=api_key, organization=org)
        context.api_key.permissions = [Permission.USAGE_READ.value]

        with patch("app.realtime.auth.ApiKeyAuthService") as mock_service:
            mock_service.return_value.authenticate = AsyncMock(return_value=context)
            principal = await authenticate_realtime_connection(
                session_factory=_FakeSessionFactory(AsyncMock()),
                token="costorah_live_abcdef123456",
                organization_id=None,
                settings=_settings(),
            )
        assert principal.kind == PrincipalKind.API_KEY
        assert principal.organization_id == org.id

    async def test_api_key_lacking_permission_rejected(self) -> None:
        org = make_org()
        api_key = MagicMock()
        api_key.id = uuid.uuid4()
        context = ApiKeyAuthContext(api_key=api_key, organization=org)
        context.api_key.permissions = []  # no usage:read scope

        with patch("app.realtime.auth.ApiKeyAuthService") as mock_service:
            mock_service.return_value.authenticate = AsyncMock(return_value=context)
            with pytest.raises(RealtimeAuthError) as exc_info:
                await authenticate_realtime_connection(
                    session_factory=_FakeSessionFactory(AsyncMock()),
                    token="costorah_live_abcdef123456",
                    organization_id=None,
                    settings=_settings(),
                )
        assert exc_info.value.reason == RealtimeAuthErrorReason.INSUFFICIENT_PERMISSIONS

    async def test_api_key_organization_mismatch_rejected(self) -> None:
        org = make_org()
        api_key = MagicMock()
        api_key.id = uuid.uuid4()
        context = ApiKeyAuthContext(api_key=api_key, organization=org)
        context.api_key.permissions = [Permission.USAGE_READ.value]

        with patch("app.realtime.auth.ApiKeyAuthService") as mock_service:
            mock_service.return_value.authenticate = AsyncMock(return_value=context)
            with pytest.raises(RealtimeAuthError) as exc_info:
                await authenticate_realtime_connection(
                    session_factory=_FakeSessionFactory(AsyncMock()),
                    token="costorah_live_abcdef123456",
                    organization_id=uuid.uuid4(),
                    settings=_settings(),
                )
        assert exc_info.value.reason == RealtimeAuthErrorReason.ORGANIZATION_MISMATCH

    async def test_invalid_api_key_rejected(self) -> None:
        with patch("app.realtime.auth.ApiKeyAuthService") as mock_service:
            mock_service.return_value.authenticate = AsyncMock(
                side_effect=InvalidApiKeyError("bad key")
            )
            with pytest.raises(RealtimeAuthError) as exc_info:
                await authenticate_realtime_connection(
                    session_factory=_FakeSessionFactory(AsyncMock()),
                    token="costorah_live_bad",
                    organization_id=None,
                    settings=_settings(),
                )
        assert exc_info.value.reason == RealtimeAuthErrorReason.INVALID_TOKEN

    async def test_expired_api_key_rejected(self) -> None:
        with patch("app.realtime.auth.ApiKeyAuthService") as mock_service:
            mock_service.return_value.authenticate = AsyncMock(
                side_effect=ApiKeyExpiredError("expired")
            )
            with pytest.raises(RealtimeAuthError) as exc_info:
                await authenticate_realtime_connection(
                    session_factory=_FakeSessionFactory(AsyncMock()),
                    token="costorah_live_expired",
                    organization_id=None,
                    settings=_settings(),
                )
        assert exc_info.value.reason == RealtimeAuthErrorReason.EXPIRED_TOKEN

    async def test_suspended_organization_rejected(self) -> None:
        with patch("app.realtime.auth.ApiKeyAuthService") as mock_service:
            mock_service.return_value.authenticate = AsyncMock(
                side_effect=OrganizationSuspendedError("suspended")
            )
            with pytest.raises(RealtimeAuthError) as exc_info:
                await authenticate_realtime_connection(
                    session_factory=_FakeSessionFactory(AsyncMock()),
                    token="costorah_live_suspended",
                    organization_id=None,
                    settings=_settings(),
                )
        assert exc_info.value.reason == RealtimeAuthErrorReason.ORGANIZATION_INACTIVE


class TestAuthenticateRealtimeConnectionJwt:
    def setup_method(self) -> None:
        self.settings = _settings()
        self.user = make_user()
        self.org = make_org()
        self.session_id = uuid.uuid4()
        self.token = create_access_token(
            user_id=str(self.user.id),
            session_id=str(self.session_id),
            email=self.user.email,
            settings=self.settings,
        )

    def _patch_repos(self):
        return (
            patch("app.realtime.auth.SessionRepository"),
            patch("app.realtime.auth.UserRepository"),
            patch("app.realtime.auth.OrganizationRepository"),
            patch("app.realtime.auth.MembershipRepository"),
        )

    async def test_valid_jwt_returns_principal(self) -> None:
        membership = make_membership(
            org_id=self.org.id, user_email=self.user.email, role=MembershipRole.MEMBER
        )
        p_session, p_user, p_org, p_membership = self._patch_repos()
        with p_session as mock_session_repo, p_user as mock_user_repo, p_org as mock_org_repo, (
            p_membership
        ) as mock_membership_repo:
            mock_session_repo.return_value.get_active = AsyncMock(return_value=object())
            mock_user_repo.return_value.get = AsyncMock(return_value=self.user)
            mock_org_repo.return_value.get = AsyncMock(return_value=self.org)
            mock_membership_repo.return_value.get_by_org_and_email = AsyncMock(
                return_value=membership
            )
            principal = await authenticate_realtime_connection(
                session_factory=_FakeSessionFactory(AsyncMock()),
                token=self.token,
                organization_id=self.org.id,
                settings=self.settings,
            )
        assert principal.kind == PrincipalKind.USER
        assert principal.principal_id == self.user.id
        assert principal.organization_id == self.org.id

    async def test_missing_organization_id_rejected(self) -> None:
        p_session, p_user, p_org, p_membership = self._patch_repos()
        with p_session as mock_session_repo, p_user as mock_user_repo, p_org, p_membership:
            mock_session_repo.return_value.get_active = AsyncMock(return_value=object())
            mock_user_repo.return_value.get = AsyncMock(return_value=self.user)
            with pytest.raises(RealtimeAuthError) as exc_info:
                await authenticate_realtime_connection(
                    session_factory=_FakeSessionFactory(AsyncMock()),
                    token=self.token,
                    organization_id=None,
                    settings=self.settings,
                )
        assert exc_info.value.reason == RealtimeAuthErrorReason.MISSING_ORGANIZATION

    async def test_revoked_session_rejected(self) -> None:
        p_session, p_user, p_org, p_membership = self._patch_repos()
        with p_session as mock_session_repo, p_user, p_org, p_membership:
            mock_session_repo.return_value.get_active = AsyncMock(return_value=None)
            with pytest.raises(RealtimeAuthError) as exc_info:
                await authenticate_realtime_connection(
                    session_factory=_FakeSessionFactory(AsyncMock()),
                    token=self.token,
                    organization_id=self.org.id,
                    settings=self.settings,
                )
        assert exc_info.value.reason == RealtimeAuthErrorReason.INVALID_TOKEN

    async def test_disabled_user_rejected(self) -> None:
        disabled = make_user(status=UserStatus.DISABLED)
        p_session, p_user, p_org, p_membership = self._patch_repos()
        with p_session as mock_session_repo, p_user as mock_user_repo, p_org, p_membership:
            mock_session_repo.return_value.get_active = AsyncMock(return_value=object())
            mock_user_repo.return_value.get = AsyncMock(return_value=disabled)
            with pytest.raises(RealtimeAuthError) as exc_info:
                await authenticate_realtime_connection(
                    session_factory=_FakeSessionFactory(AsyncMock()),
                    token=self.token,
                    organization_id=self.org.id,
                    settings=self.settings,
                )
        assert exc_info.value.reason == RealtimeAuthErrorReason.USER_DISABLED

    async def test_not_a_member_rejected(self) -> None:
        p_session, p_user, p_org, p_membership = self._patch_repos()
        with p_session as mock_session_repo, p_user as mock_user_repo, p_org as mock_org_repo, (
            p_membership
        ) as mock_membership_repo:
            mock_session_repo.return_value.get_active = AsyncMock(return_value=object())
            mock_user_repo.return_value.get = AsyncMock(return_value=self.user)
            mock_org_repo.return_value.get = AsyncMock(return_value=self.org)
            mock_membership_repo.return_value.get_by_org_and_email = AsyncMock(return_value=None)
            with pytest.raises(RealtimeAuthError) as exc_info:
                await authenticate_realtime_connection(
                    session_factory=_FakeSessionFactory(AsyncMock()),
                    token=self.token,
                    organization_id=self.org.id,
                    settings=self.settings,
                )
        assert exc_info.value.reason == RealtimeAuthErrorReason.NOT_A_MEMBER

    async def test_suspended_organization_rejected(self) -> None:
        suspended_org = make_org(status=OrganizationStatus.SUSPENDED)
        p_session, p_user, p_org, p_membership = self._patch_repos()
        with p_session as mock_session_repo, p_user as mock_user_repo, p_org as mock_org_repo, (
            p_membership
        ):
            mock_session_repo.return_value.get_active = AsyncMock(return_value=object())
            mock_user_repo.return_value.get = AsyncMock(return_value=self.user)
            mock_org_repo.return_value.get = AsyncMock(return_value=suspended_org)
            with pytest.raises(RealtimeAuthError) as exc_info:
                await authenticate_realtime_connection(
                    session_factory=_FakeSessionFactory(AsyncMock()),
                    token=self.token,
                    organization_id=suspended_org.id,
                    settings=self.settings,
                )
        assert exc_info.value.reason == RealtimeAuthErrorReason.ORGANIZATION_INACTIVE

    async def test_organization_not_found_rejected(self) -> None:
        p_session, p_user, p_org, p_membership = self._patch_repos()
        with p_session as mock_session_repo, p_user as mock_user_repo, p_org as mock_org_repo, (
            p_membership
        ):
            mock_session_repo.return_value.get_active = AsyncMock(return_value=object())
            mock_user_repo.return_value.get = AsyncMock(return_value=self.user)
            mock_org_repo.return_value.get = AsyncMock(return_value=None)
            with pytest.raises(RealtimeAuthError) as exc_info:
                await authenticate_realtime_connection(
                    session_factory=_FakeSessionFactory(AsyncMock()),
                    token=self.token,
                    organization_id=uuid.uuid4(),
                    settings=self.settings,
                )
        assert exc_info.value.reason == RealtimeAuthErrorReason.ORGANIZATION_NOT_FOUND

    async def test_expired_token_rejected(self) -> None:
        with patch(
            "app.realtime.auth.decode_access_token", side_effect=ExpiredSignatureError()
        ):
            with pytest.raises(RealtimeAuthError) as exc_info:
                await authenticate_realtime_connection(
                    session_factory=_FakeSessionFactory(AsyncMock()),
                    token="whatever",
                    organization_id=self.org.id,
                    settings=self.settings,
                )
        assert exc_info.value.reason == RealtimeAuthErrorReason.EXPIRED_TOKEN

    async def test_malformed_token_rejected(self) -> None:
        with pytest.raises(RealtimeAuthError) as exc_info:
            await authenticate_realtime_connection(
                session_factory=_FakeSessionFactory(AsyncMock()),
                token="not.a.jwt",
                organization_id=self.org.id,
                settings=self.settings,
            )
        assert exc_info.value.reason == RealtimeAuthErrorReason.INVALID_TOKEN

    async def test_role_lacking_permission_rejected(self) -> None:
        # A membership with a role that has no permissions at all cannot
        # open a real-time connection, matching the existing RBAC matrix.
        membership = make_membership(
            org_id=self.org.id, user_email=self.user.email, role=MembershipRole.MEMBER
        )
        p_session, p_user, p_org, p_membership = self._patch_repos()
        with p_session as mock_session_repo, p_user as mock_user_repo, p_org as mock_org_repo, (
            p_membership
        ) as mock_membership_repo:
            mock_session_repo.return_value.get_active = AsyncMock(return_value=object())
            mock_user_repo.return_value.get = AsyncMock(return_value=self.user)
            mock_org_repo.return_value.get = AsyncMock(return_value=self.org)
            mock_membership_repo.return_value.get_by_org_and_email = AsyncMock(
                return_value=membership
            )
            with patch("app.realtime.auth.has_permission", return_value=False):
                with pytest.raises(RealtimeAuthError) as exc_info:
                    await authenticate_realtime_connection(
                        session_factory=_FakeSessionFactory(AsyncMock()),
                        token=self.token,
                        organization_id=self.org.id,
                        settings=self.settings,
                    )
        assert exc_info.value.reason == RealtimeAuthErrorReason.INSUFFICIENT_PERMISSIONS


# ─── WebSocket + SSE gateway (integration) ────────────────────────────────────


def _app_with_container(container: AppContainer) -> FastAPI:
    settings = container.settings
    app = create_app(settings)
    app.state.container = container
    return app


def _mock_container() -> AppContainer:
    settings = _settings()
    redis = AsyncMock()
    event_bus = EventBus(redis)
    connection_manager = ConnectionManager(event_bus)
    rate_limiter = ConnectionRateLimiter(redis=None)
    return AppContainer(
        settings=settings,
        engine=MagicMock(),
        session_factory=MagicMock(),
        redis=redis,
        event_bus=event_bus,
        connection_manager=connection_manager,
        realtime_rate_limiter=rate_limiter,
    )


class TestWebSocketGateway:
    def test_connect_receive_and_disconnect(self) -> None:
        container = _mock_container()
        app = _app_with_container(container)
        org_id = uuid.uuid4()
        principal = MagicMock()
        principal.kind = PrincipalKind.USER
        principal.principal_id = uuid.uuid4()
        principal.organization_id = org_id

        with patch(
            "app.api.v1.realtime.authenticate_realtime_connection",
            AsyncMock(return_value=principal),
        ):
            client = TestClient(app)
            with client.websocket_connect("/v1/ws?token=whatever&organization_id="
                                           f"{org_id}") as ws:
                assert container.connection_manager.connection_count(org_id) == 1
                container.connection_manager.dispatch(org_id, _event(org_id))
                message = ws.receive_text()
                assert "usage.created" in message

        # Connection cleaned up after the `with` block closes the socket.
        assert container.connection_manager.connection_count(org_id) == 0

    def test_auth_failure_closes_connection(self) -> None:
        container = _mock_container()
        app = _app_with_container(container)

        with patch(
            "app.api.v1.realtime.authenticate_realtime_connection",
            AsyncMock(
                side_effect=RealtimeAuthError(
                    RealtimeAuthErrorReason.INVALID_TOKEN, "nope"
                )
            ),
        ):
            client = TestClient(app)
            from starlette.websockets import WebSocketDisconnect

            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect("/v1/ws?token=bad") as ws:
                    ws.receive_text()

    def test_rate_limited_connection_is_rejected(self) -> None:
        container = _mock_container()
        container.realtime_rate_limiter = ConnectionRateLimiter(redis=None, max_attempts=0)
        app = _app_with_container(container)

        with patch(
            "app.api.v1.realtime.authenticate_realtime_connection",
            AsyncMock(),
        ):
            client = TestClient(app)
            from starlette.websockets import WebSocketDisconnect

            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect("/v1/ws?token=x") as ws:
                    ws.receive_text()

    def test_organization_isolation_over_the_wire(self) -> None:
        """Events dispatched for org B never arrive on org A's live socket."""
        container = _mock_container()
        app = _app_with_container(container)
        org_a, org_b = uuid.uuid4(), uuid.uuid4()
        principal = MagicMock()
        principal.kind = PrincipalKind.USER
        principal.principal_id = uuid.uuid4()
        principal.organization_id = org_a

        with patch(
            "app.api.v1.realtime.authenticate_realtime_connection",
            AsyncMock(return_value=principal),
        ):
            client = TestClient(app)
            with client.websocket_connect(f"/v1/ws?token=t&organization_id={org_a}") as ws:
                container.connection_manager.dispatch(org_b, _event(org_b))
                container.connection_manager.dispatch(org_a, _event(org_a, trace_id="mine"))
                message = ws.receive_text()
                assert '"trace_id":"mine"' in message


class TestSSEEndpoint:
    async def test_reconnect_replays_events_since_last_event_id(self) -> None:
        """Last-Event-ID reconnect: buffered events are replayed immediately,
        proving the reconnect-replay path without depending on real-time
        dispatch timing across the ASGI test transport."""
        container = _mock_container()
        app = _app_with_container(container)
        org_id = uuid.uuid4()
        principal = MagicMock()
        principal.kind = PrincipalKind.API_KEY
        principal.principal_id = uuid.uuid4()
        principal.organization_id = org_id
        replayed = _event(org_id, trace_id="replayed-one")

        with (
            patch(
                "app.api.v1.realtime.authenticate_realtime_connection",
                AsyncMock(return_value=principal),
            ),
            patch.object(
                container.event_bus, "replay_since", AsyncMock(return_value=[replayed])
            ),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                async with ac.stream(
                    "GET",
                    f"/v1/events?token=x&organization_id={org_id}",
                    headers={"Last-Event-ID": str(uuid.uuid4())},
                ) as response:
                    assert response.status_code == 200
                    chunk = b""
                    async for part in response.aiter_bytes():
                        chunk += part
                        if b"\n\n" in chunk:
                            break
        assert b"event: usage.created" in chunk
        assert b"replayed-one" in chunk

    async def test_auth_failure_returns_401(self) -> None:
        container = _mock_container()
        app = _app_with_container(container)

        with patch(
            "app.api.v1.realtime.authenticate_realtime_connection",
            AsyncMock(
                side_effect=RealtimeAuthError(
                    RealtimeAuthErrorReason.MISSING_TOKEN, "no token"
                )
            ),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                response = await ac.get("/v1/events")
        assert response.status_code == 401

    async def test_rate_limited_returns_429(self) -> None:
        container = _mock_container()
        container.realtime_rate_limiter = ConnectionRateLimiter(redis=None, max_attempts=0)
        app = _app_with_container(container)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/v1/events?token=x")
        assert response.status_code == 429


# ─── usage.created emission wiring ─────────────────────────────────────────────


class TestUsageCreatedEmission:
    async def test_ingest_publishes_usage_created_when_not_duplicate(self) -> None:
        from app.api.v1 import ingest as ingest_module
        from tests.conftest import make_usage_record

        record = make_usage_record()
        event_bus = AsyncMock()
        db = AsyncMock()
        current_api_key = MagicMock()
        current_api_key.organization_id = record.organization_id
        current_api_key.api_key_id = uuid.uuid4()

        with patch.object(
            ingest_module.UsageIngestionService,
            "ingest",
            AsyncMock(return_value=(record, False)),
        ):
            body = MagicMock()
            await ingest_module.ingest_usage(
                body=body, db=db, event_bus=event_bus, current_api_key=current_api_key
            )

        event_bus.publish.assert_awaited_once()
        published_event = event_bus.publish.await_args.args[0]
        assert published_event.type == EventType.USAGE_CREATED
        assert published_event.organization_id == record.organization_id

    async def test_ingest_does_not_publish_for_duplicate(self) -> None:
        from app.api.v1 import ingest as ingest_module
        from tests.conftest import make_usage_record

        record = make_usage_record()
        event_bus = AsyncMock()
        db = AsyncMock()
        current_api_key = MagicMock()
        current_api_key.organization_id = record.organization_id
        current_api_key.api_key_id = uuid.uuid4()

        with patch.object(
            ingest_module.UsageIngestionService,
            "ingest",
            AsyncMock(return_value=(record, True)),
        ):
            body = MagicMock()
            await ingest_module.ingest_usage(
                body=body, db=db, event_bus=event_bus, current_api_key=current_api_key
            )

        event_bus.publish.assert_not_awaited()
