"""Tests for EP-24.6.1 — Authentication Completion & WebSocket Stability
(production hotfix).

Covers the three issues this EP fixes:

Issue 1 — Google Sign-In no longer skips password setup:
  - `UserPublic.password_configured` is derived from `password_hash is not
    None`, never a new column.
  - `AuthService.set_password()` sets a first password for a Google-only
    account, and refuses (`PasswordAlreadyConfiguredError`) once one exists.
  - `POST /v1/auth/set-password` — 200 on success, 409 when already
    configured, 401 unauthenticated.

Issue 2 — `register()` no longer issues a session:
  - `AuthService.register()` returns `(None, user, org)` — no `TokenPair`,
    no `Session` row created.
  - `POST /v1/auth/register` returns no token fields and
    `email_verification_required: true`.
  - The full register -> (no session) -> login-rejected -> verify ->
    login-succeeds journey.
  - Google OAuth registration is unaffected (still issues a session
    immediately — Google already verified the email).

Issue 3 — WebSocket close codes now survive to a real browser:
  - `websocket.accept()` is sent before any `websocket.close(code=...)`,
    verified via a raw ASGI harness that inspects the literal message
    order the app sends (not just the final code Starlette's in-process
    `TestClient` hands back, which — per this EP's own root-cause finding
    — delivers the intended code regardless of accept order, masking the
    real bug that only manifests over a real HTTP/WS upgrade).
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.auth.exceptions import PasswordAlreadyConfiguredError
from app.auth.password import hash_password, verify_password
from app.auth.service import AuthService
from app.config.settings import Settings
from app.core.container import AppContainer
from app.main import create_app
from app.realtime.auth import RealtimeAuthError, RealtimeAuthErrorReason
from app.realtime.connection_manager import ConnectionManager
from app.realtime.event_bus import EventBus
from app.realtime.rate_limit import ConnectionRateLimiter
from tests.conftest import make_user

_TEST_PASSWORD = "correct-horse-battery-staple"


def _test_settings(**overrides: Any) -> Settings:
    kwargs: dict[str, Any] = {
        "app_env": "testing",
        "app_secret_key": "test-secret-key-with-at-least-32-chars!!",
        "jwt_secret": "test-jwt-secret-for-unit-tests-only!!",
    }
    kwargs.update(overrides)
    return Settings(**kwargs)


def _make_svc() -> AuthService:
    svc = AuthService(AsyncMock(), _test_settings())
    svc._user_repo = AsyncMock()
    svc._session_repo = AsyncMock()
    svc._membership_repo = AsyncMock()
    svc._org_repo = AsyncMock()
    # unique_slug() loops "while slug_exists(candidate)" — an unconfigured
    # AsyncMock's return value is truthy, which would loop forever.
    svc._org_repo.slug_exists = AsyncMock(return_value=False)
    # register() -> _send_verification_email() -> create_verification_token()
    # would otherwise run against the real VerificationTokenRepository bound
    # to the outer AsyncMock() session, calling the (sync) session.add() as
    # if it were async and leaving an unawaited-coroutine warning.
    svc._verify_repo = AsyncMock()
    svc._email = AsyncMock()
    return svc


# ─── Issue 1 — mandatory password setup for Google-only accounts ─────────────


class TestSetPassword:
    @pytest.mark.asyncio
    async def test_sets_first_password_for_google_only_account(self) -> None:
        svc = _make_svc()
        user = make_user(password_hash=None)

        await svc.set_password(user=user, new_password=_TEST_PASSWORD)

        assert user.password_hash is not None
        assert verify_password(user.password_hash, _TEST_PASSWORD)

    @pytest.mark.asyncio
    async def test_refuses_when_password_already_configured(self) -> None:
        svc = _make_svc()
        user = make_user(password_hash=hash_password("already-set-password"))

        with pytest.raises(PasswordAlreadyConfiguredError):
            await svc.set_password(user=user, new_password=_TEST_PASSWORD)

        # The existing password must survive an attempted overwrite.
        assert verify_password(user.password_hash, "already-set-password")

    @pytest.mark.asyncio
    async def test_does_not_revoke_other_sessions(self) -> None:
        """Unlike change_password, there is no prior credential to treat as
        potentially compromised — no session-revocation side effect."""
        svc = _make_svc()
        user = make_user(password_hash=None)

        await svc.set_password(user=user, new_password=_TEST_PASSWORD)

        svc._session_repo.revoke_all_for_user_except.assert_not_awaited()
        svc._session_repo.revoke_all_for_user.assert_not_awaited()


class TestPasswordConfiguredField:
    def test_true_for_password_account(self) -> None:
        from app.api.v1.auth import _build_user_public

        user = make_user(password_hash=hash_password(_TEST_PASSWORD))
        assert _build_user_public(user).password_configured is True

    def test_false_for_google_only_account(self) -> None:
        from app.api.v1.auth import _build_user_public

        user = make_user(password_hash=None)
        assert _build_user_public(user).password_configured is False


class TestSetPasswordEndpoint:
    @pytest.mark.asyncio
    async def test_returns_409_when_already_configured(self) -> None:
        from app.api.deps import get_db, get_settings
        from app.auth.dependencies import get_current_user

        app: FastAPI = create_app(_test_settings())
        user = make_user(password_hash=hash_password("existing"))
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: AsyncMock()
        app.dependency_overrides[get_settings] = lambda: _test_settings()

        with patch(
            "app.api.v1.auth.AuthService.set_password",
            AsyncMock(side_effect=PasswordAlreadyConfiguredError),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/v1/auth/set-password", json={"new_password": _TEST_PASSWORD}
                )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_returns_401_unauthenticated(self) -> None:
        from app.api.deps import get_db, get_settings

        app: FastAPI = create_app(_test_settings())
        # get_current_user's own signature needs `db: DbDep` resolved
        # regardless of whether a token is present — FastAPI resolves
        # sibling parameters before the dependency body runs, so `get_db`
        # (which needs `request.app.state.container`) must be overridden
        # here too, even though this test never reaches the DB.
        app.dependency_overrides[get_db] = lambda: AsyncMock()
        app.dependency_overrides[get_settings] = lambda: _test_settings()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/v1/auth/set-password", json={"new_password": _TEST_PASSWORD})
        assert resp.status_code == 401
        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_succeeds_and_returns_password_configured_true(self) -> None:
        from app.api.deps import get_db, get_settings
        from app.auth.dependencies import get_current_user

        app: FastAPI = create_app(_test_settings())
        user = make_user(password_hash=None)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: AsyncMock()
        app.dependency_overrides[get_settings] = lambda: _test_settings()

        async def _fake_set_password(self: Any, *, user: Any, new_password: str) -> None:
            user.password_hash = hash_password(new_password)

        with patch("app.api.v1.auth.AuthService.set_password", _fake_set_password):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/v1/auth/set-password", json={"new_password": _TEST_PASSWORD}
                )
        assert resp.status_code == 200
        assert resp.json()["password_configured"] is True

        app.dependency_overrides.clear()


# ─── Issue 2 — register() no longer issues a session ─────────────────────────


class TestRegisterDoesNotIssueSession:
    @pytest.mark.asyncio
    async def test_register_returns_no_token_pair(self) -> None:
        svc = _make_svc()
        svc._user_repo.email_exists.return_value = False
        svc._membership_repo.create = AsyncMock()

        pair, user, _org = await svc.register(
            email="new@example.com", password=_TEST_PASSWORD, display_name="New User"
        )

        assert pair is None
        assert user.email_verified is False
        assert user.password_hash is not None
        svc._session_repo.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_register_still_sends_verification_email(self) -> None:
        svc = _make_svc()
        svc._user_repo.email_exists.return_value = False
        svc._membership_repo.create = AsyncMock()
        svc._verify_repo = AsyncMock()

        await svc.register(
            email="new@example.com", password=_TEST_PASSWORD, display_name="New User"
        )

        svc._email.send_verification_email.assert_awaited_once()


class TestRegisterEndpoint:
    @pytest.mark.asyncio
    async def test_response_has_no_tokens_and_requires_verification(self) -> None:
        from app.api.deps import get_db, get_settings

        app: FastAPI = create_app(_test_settings())
        app.dependency_overrides[get_db] = lambda: AsyncMock()
        app.dependency_overrides[get_settings] = lambda: _test_settings()

        user = make_user(email="new@example.com", password_hash=hash_password(_TEST_PASSWORD))
        org = MagicMock()
        org.external_id = "org_ext"
        org.name = "New User's Workspace"
        org.slug = "new-users-workspace"
        org.is_personal = True

        with patch(
            "app.api.v1.auth.AuthService.register",
            AsyncMock(return_value=(None, user, org)),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/v1/auth/register",
                    json={
                        "email": "new@example.com",
                        "password": _TEST_PASSWORD,
                        "display_name": "New User",
                    },
                )
        assert resp.status_code == 201
        body = resp.json()
        assert body["access_token"] is None
        assert body["refresh_token"] is None
        assert body["email_verification_required"] is True
        assert body["user"]["email_verified"] is False
        # No session cookie either.
        assert "costorah_access_token" not in resp.cookies

        app.dependency_overrides.clear()


class TestFullRegisterVerifyLoginJourney:
    @pytest.mark.asyncio
    async def test_register_then_login_rejected_then_verify_then_login_succeeds(self) -> None:
        """The exact journey Issue 2's spec describes end to end at the
        service layer (mirrors test_ep24_4_1's precedent, updated for
        register() no longer issuing a session of its own)."""
        svc = _make_svc()
        svc._user_repo.email_exists.return_value = False
        svc._membership_repo.create = AsyncMock()

        pair, user, _org = await svc.register(
            email="journey@example.com", password=_TEST_PASSWORD, display_name="Journey"
        )
        assert pair is None
        assert user.email_verified is False

        # A login attempt right after registering must still be rejected.
        svc._user_repo.get_by_email.return_value = user
        from app.auth.exceptions import EmailNotVerifiedError

        with pytest.raises(EmailNotVerifiedError):
            await svc.login(email=user.email, password=_TEST_PASSWORD)

        # Verifying flips the flag (mirrors AuthService.verify_email's own
        # mutation, done directly here since the token plumbing is covered
        # by test_ep24_4_email_auth.py).
        user.email_verified = True

        login_pair, logged_in_user = await svc.login(email=user.email, password=_TEST_PASSWORD)
        assert login_pair is not None
        assert logged_in_user.email_verified is True


class TestGoogleRegistrationUnaffected:
    @pytest.mark.asyncio
    async def test_google_registration_still_issues_a_session(self) -> None:
        """Google-verified accounts are the one deliberate exception to
        Issue 2 — the email is already verified, so a session is still
        issued immediately (unchanged from EP-24.5)."""
        svc = _make_svc()
        svc._user_repo.get_by_google_sub.return_value = None
        svc._user_repo.get_by_email.return_value = None
        svc._membership_repo.create = AsyncMock()
        svc._membership_repo.link_pending_by_email = AsyncMock()

        pair, user, org, is_new = await svc.login_or_register_with_google(
            google_sub="google-sub-1",
            email="googler@example.com",
            display_name="Googler",
            avatar_url=None,
        )

        assert pair is not None
        assert is_new is True
        assert user.email_verified is True
        assert org is not None


# ─── Issue 3 — WebSocket accept() must precede close(code=...) ───────────────


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


def _app_with_container(container: AppContainer) -> FastAPI:
    app = create_app(container.settings)
    app.state.container = container
    return app


class _RawWebSocketHarness:
    """Drives an ASGI app's websocket route directly (bypassing Starlette's
    `TestClient`), so the literal sequence of outgoing ASGI messages —
    `websocket.accept` vs. `websocket.close` and their order — can be
    inspected. `TestClient.websocket_connect` cannot distinguish "closed
    with the right code before accept" from "closed with the right code
    after accept": its `WebSocketTestSession` hands back whatever code the
    app sent regardless of ordering, which is exactly why the EP-24.6.1
    root-cause writeup singles it out as the reason the pre-existing
    `test_ep19_1.py` suite passed despite the bug.
    """

    def __init__(self, app: FastAPI, path: str) -> None:
        self._app = app
        self._path = path
        self.sent: list[dict[str, Any]] = []
        self._to_receive: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._to_receive.put_nowait({"type": "websocket.connect"})
        # After the app sends its first close/disconnect-triggering message
        # the handler returns, so a second receive is never actually
        # awaited in the failure paths this test exercises — but the
        # connect/dispatch path needs one, so queue a disconnect too.
        self._to_receive.put_nowait({"type": "websocket.disconnect", "code": 1000})

    async def run(self, query_string: bytes = b"") -> None:
        scope = {
            "type": "websocket",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "scheme": "ws",
            "path": self._path,
            "raw_path": self._path.encode(),
            "query_string": query_string,
            "root_path": "",
            "headers": [],
            "client": ("testclient", 12345),
            "server": ("testserver", 80),
            "subprotocols": [],
        }

        async def receive() -> dict[str, Any]:
            return await self._to_receive.get()

        async def send(message: dict[str, Any]) -> None:
            self.sent.append(message)

        await self._app(scope, receive, send)


class TestWebSocketAcceptBeforeClose:
    @pytest.mark.asyncio
    async def test_rate_limited_connection_accepts_before_closing(self) -> None:
        container = _mock_container()
        container.realtime_rate_limiter = ConnectionRateLimiter(redis=None, max_attempts=0)
        app = _app_with_container(container)

        with patch("app.api.v1.realtime.authenticate_realtime_connection", AsyncMock()):
            harness = _RawWebSocketHarness(app, "/v1/ws")
            await harness.run(query_string=b"token=x")

        types = [m["type"] for m in harness.sent]
        assert types[0] == "websocket.accept", (
            "accept() must be the first ASGI message sent — sending "
            "websocket.close first means the real close code never "
            "reaches a browser (see app/api/v1/realtime.py's docstring)"
        )
        assert "websocket.close" in types
        close_msg = next(m for m in harness.sent if m["type"] == "websocket.close")
        assert close_msg["code"] == 4429

    @pytest.mark.asyncio
    async def test_auth_failure_accepts_before_closing(self) -> None:
        container = _mock_container()
        app = _app_with_container(container)

        with patch(
            "app.api.v1.realtime.authenticate_realtime_connection",
            AsyncMock(side_effect=RealtimeAuthError(RealtimeAuthErrorReason.INVALID_TOKEN, "nope")),
        ):
            harness = _RawWebSocketHarness(app, "/v1/ws")
            await harness.run(query_string=b"token=bad")

        types = [m["type"] for m in harness.sent]
        assert types[0] == "websocket.accept"
        close_msg = next(m for m in harness.sent if m["type"] == "websocket.close")
        assert close_msg["code"] == 4401

    @pytest.mark.asyncio
    async def test_successful_connection_still_accepts_first(self) -> None:
        """Regression guard: the fix must not change the happy path's
        message order — accept is still the very first thing sent.

        A successful connection then blocks forever on the 30s-heartbeat /
        event-forwarding loop (`app/api/v1/realtime.py`'s own long-lived
        `asyncio.wait(..., FIRST_COMPLETED)`), which this harness's tiny
        receive queue can't sustain — so the handler task is cancelled
        shortly after `accept()` is sent, which is all this test needs to
        observe.
        """
        container = _mock_container()
        app = _app_with_container(container)
        org_id = uuid.uuid4()
        principal = MagicMock()
        principal.organization_id = org_id

        with patch(
            "app.api.v1.realtime.authenticate_realtime_connection",
            AsyncMock(return_value=principal),
        ):
            harness = _RawWebSocketHarness(app, "/v1/ws")
            task = asyncio.ensure_future(
                harness.run(query_string=f"token=good&organization_id={org_id}".encode())
            )
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=0.2)
            except TimeoutError:
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task

        assert harness.sent[0]["type"] == "websocket.accept"
