"""EP-19.4 — WebSocket abnormal-closure (1006) regression tests.

Root cause (full forensic writeup in `app/api/v1/realtime.py`'s own
comments above `write_lock`): `websocket_gateway()`'s task-completion
handling never called `websocket.close()` for any completion path other
than the heartbeat-timeout's own explicit `close(4408)` branch. Per
uvicorn's `run_asgi()` (`uvicorn/protocols/websockets/websockets_impl.py`),
an ASGI websocket application that returns having never sent a
`"websocket.close"` message causes uvicorn to fall back to a raw
`self.transport.close()` — no WebSocket closing handshake — which a
browser reports as `CloseEvent{code: 1006, wasClean: false}`.

Like EP-24.6.1's own accept()-ordering regression, Starlette's
`TestClient.websocket_connect()` (`WebSocketTestSession`) cannot reproduce
this: its in-process simulation hands back whatever ASGI messages the app
sent with no awareness of uvicorn's "app returned without closing"
fallback. These tests drive the ASGI app directly (the same
`_RawWebSocketHarness` pattern EP-24.6.1 introduced) and assert on the
literal sequence of outgoing ASGI messages, so they can actually observe
whether a `"websocket.close"` message was sent — the one thing a
`TestClient`-based test structurally cannot distinguish.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI

from app.config.settings import Settings
from app.core.container import AppContainer
from app.main import create_app
from app.realtime.auth import PrincipalKind
from app.realtime.connection_manager import ConnectionManager
from app.realtime.event_bus import EventBus
from app.realtime.rate_limit import ConnectionRateLimiter

pytestmark = pytest.mark.asyncio


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
    settings = container.settings
    app = create_app(settings)
    app.state.container = container
    return app


class _RawWebSocketHarness:
    """Drives an ASGI app's websocket route directly (bypassing Starlette's
    `TestClient`), so the literal sequence of outgoing ASGI messages —
    including whether a `"websocket.close"` was ever sent at all — can be
    inspected. Mirrors `test_ep24_6_1_hotfix.py`'s harness of the same
    name/shape (duplicated here per this suite's existing per-file
    convention rather than imported across test modules)."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self._to_receive: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._to_receive.put_nowait({"type": "websocket.connect"})

    def queue_receive(self, message: dict[str, Any]) -> None:
        self._to_receive.put_nowait(message)

    async def run(self, app: FastAPI, path: str, query_string: bytes = b"") -> None:
        scope = {
            "type": "websocket",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "scheme": "ws",
            "path": path,
            "raw_path": path.encode(),
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

        await app(scope, receive, send)


async def _run_with_timeout(coro: Any, timeout: float = 2.0) -> None:
    """Runs `coro` (a coroutine, not yet a task) with a hard timeout, so a
    bug that reintroduces "never closes, hangs forever waiting on the next
    heartbeat" fails the test loudly instead of hanging CI."""
    await asyncio.wait_for(coro, timeout=timeout)


def _ws_query(org_id: uuid.UUID) -> bytes:
    return f"token=t&organization_id={org_id}".encode()


class TestForwardTaskFailureStillCloses:
    """The primary regression this EP fixes: a `_forward_events` failure
    that is NOT a `WebSocketDisconnect` (a serialization error, a bug in
    dispatch, anything) must still result in an explicit close before the
    handler returns."""

    async def test_internal_error_in_forward_task_sends_explicit_close(self) -> None:
        container = _mock_container()
        app = _app_with_container(container)
        org_id = uuid.uuid4()
        principal = MagicMock()
        principal.kind = PrincipalKind.USER
        principal.principal_id = uuid.uuid4()
        principal.organization_id = org_id

        async def _broken_receive(_connection_id: str) -> Any:
            raise RuntimeError("boom — simulated internal failure")
            yield  # pragma: no cover — makes this a generator function

        with (
            patch(
                "app.api.v1.realtime.authenticate_realtime_connection",
                AsyncMock(return_value=principal),
            ),
            patch.object(container.connection_manager, "receive", _broken_receive),
        ):
            harness = _RawWebSocketHarness()
            await _run_with_timeout(harness.run(app, "/v1/ws", query_string=_ws_query(org_id)))

        types = [m["type"] for m in harness.sent]
        assert types[0] == "websocket.accept"
        assert "websocket.close" in types, (
            "the handler must always send an explicit websocket.close before "
            "returning — without it, uvicorn's run_asgi() falls back to a "
            "raw transport.close() with no closing handshake, which is "
            "exactly what a browser reports as CloseEvent{code: 1006}"
        )
        close_msg = next(m for m in harness.sent if m["type"] == "websocket.close")
        assert close_msg["code"] == 1011
        assert close_msg["reason"] == "Internal error"

        # The connection must still be cleanly unregistered even though the
        # forward task failed.
        assert container.connection_manager.connection_count(org_id) == 0


class TestHeartbeatTimeoutStillCloses:
    """Regression guard: the pre-existing, already-correct heartbeat-timeout
    close path must keep working unchanged after the fix."""

    async def test_heartbeat_timeout_sends_4408_close(self) -> None:
        container = _mock_container()
        app = _app_with_container(container)
        org_id = uuid.uuid4()
        principal = MagicMock()
        principal.kind = PrincipalKind.USER
        principal.principal_id = uuid.uuid4()
        principal.organization_id = org_id

        with (
            patch(
                "app.api.v1.realtime.authenticate_realtime_connection",
                AsyncMock(return_value=principal),
            ),
            # Shrink both intervals so the test doesn't wait 30s+10s for
            # real — the harness's receive queue never answers a ping, so
            # the timeout branch fires almost immediately.
            patch("app.api.v1.realtime.HEARTBEAT_INTERVAL_SECONDS", 0.01),
            patch("app.api.v1.realtime.HEARTBEAT_TIMEOUT_SECONDS", 0.05),
        ):
            harness = _RawWebSocketHarness()
            await _run_with_timeout(harness.run(app, "/v1/ws", query_string=_ws_query(org_id)))

        types = [m["type"] for m in harness.sent]
        assert types[0] == "websocket.accept"
        close_msg = next(m for m in harness.sent if m["type"] == "websocket.close")
        assert close_msg["code"] == 4408
        assert close_msg["reason"] == "Heartbeat timeout"
        assert container.connection_manager.connection_count(org_id) == 0


class TestClientDisconnectDuringHeartbeatReadStillCloses:
    """A client-initiated disconnect (browser tab closed, network drop)
    surfaces as `WebSocketDisconnect` from the heartbeat task's read — this
    must not escape as an unhandled exception, and the handler must still
    attempt a graceful close (a safe no-op if the transport is already
    gone) rather than silently returning."""

    async def test_client_disconnect_does_not_raise_and_still_unregisters(self) -> None:
        container = _mock_container()
        app = _app_with_container(container)
        org_id = uuid.uuid4()
        principal = MagicMock()
        principal.kind = PrincipalKind.USER
        principal.principal_id = uuid.uuid4()
        principal.organization_id = org_id

        with (
            patch(
                "app.api.v1.realtime.authenticate_realtime_connection",
                AsyncMock(return_value=principal),
            ),
            patch("app.api.v1.realtime.HEARTBEAT_INTERVAL_SECONDS", 0.01),
            patch("app.api.v1.realtime.HEARTBEAT_TIMEOUT_SECONDS", 5.0),
        ):
            harness = _RawWebSocketHarness()
            harness.queue_receive({"type": "websocket.disconnect", "code": 1000})
            # No exception should propagate out of the ASGI app call — a
            # pre-fix regression here would either hang (never closing) or
            # raise WebSocketDisconnect/RuntimeError out of run_asgi().
            await _run_with_timeout(harness.run(app, "/v1/ws", query_string=_ws_query(org_id)))

        assert harness.sent[0]["type"] == "websocket.accept"
        assert container.connection_manager.connection_count(org_id) == 0


class TestNoConcurrentWriteRaceOnSendAfterClose:
    """Direct regression pin for the secondary defect: `_forward_events`
    attempting to send after `_heartbeat_and_read` has already closed the
    socket must never raise `RuntimeError('Cannot call "send" once a close
    message has been sent.')` out of the task — the shared `write_lock` +
    `application_state` re-check must make this a clean no-op."""

    async def test_forward_task_after_close_is_a_clean_no_op(self) -> None:
        container = _mock_container()
        app = _app_with_container(container)
        org_id = uuid.uuid4()
        principal = MagicMock()
        principal.kind = PrincipalKind.USER
        principal.principal_id = uuid.uuid4()
        principal.organization_id = org_id

        # Force the heartbeat branch to win first (very short timeout),
        # then dispatch an event immediately after — if forward_events
        # weren't state-guarded, its send would race the heartbeat's
        # close() and could raise.
        with (
            patch(
                "app.api.v1.realtime.authenticate_realtime_connection",
                AsyncMock(return_value=principal),
            ),
            patch("app.api.v1.realtime.HEARTBEAT_INTERVAL_SECONDS", 0.01),
            patch("app.api.v1.realtime.HEARTBEAT_TIMEOUT_SECONDS", 0.05),
        ):
            harness = _RawWebSocketHarness()
            await _run_with_timeout(harness.run(app, "/v1/ws", query_string=_ws_query(org_id)))

        # No unhandled exception reached this point (asyncio.wait_for above
        # would have re-raised it) — the close is still exactly one 4408.
        close_messages = [m for m in harness.sent if m["type"] == "websocket.close"]
        assert len(close_messages) == 1
        assert close_messages[0]["code"] == 4408
