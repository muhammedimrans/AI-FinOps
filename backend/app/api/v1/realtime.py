"""Real-Time Gateway — EP-19.1.

Endpoints:
  GET /v1/ws     — WebSocket gateway (JWT or API Key, `?token=` or
                    `Authorization: Bearer` header)
  GET /v1/events — Server-Sent Events endpoint, same auth, supports
                    `Last-Event-ID` for reconnect replay

Both endpoints reuse `app.realtime.auth.authenticate_realtime_connection`
for authentication (no new auth system) and
`app.realtime.connection_manager.ConnectionManager` for registration,
dispatch, and organization isolation. Neither endpoint touches the
existing polling APIs — this is purely additive.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator

import structlog
from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import StreamingResponse
from starlette.websockets import WebSocketState

from app.core.container import AppContainer
from app.realtime.auth import RealtimeAuthError, authenticate_realtime_connection, extract_token
from app.realtime.connection_manager import ConnectionKind
from app.realtime.events import RealtimeEvent
from app.realtime.metrics import heartbeat_failures_total, reconnects_total

log = structlog.get_logger(__name__)

router = APIRouter(tags=["realtime"])

HEARTBEAT_INTERVAL_SECONDS = 30
HEARTBEAT_TIMEOUT_SECONDS = 10


def _format_sse(event: RealtimeEvent) -> bytes:
    return (
        f"id: {event.event_id}\nevent: {event.type.value}\ndata: {event.model_dump_json()}\n\n"
    ).encode()


@router.websocket("/ws")
async def websocket_gateway(
    websocket: WebSocket,
    token: str | None = Query(default=None),
    organization_id: uuid.UUID | None = Query(default=None),
) -> None:
    container: AppContainer = websocket.app.state.container
    ip = websocket.client.host if websocket.client else None

    # EP-24.6.1 — Issue 3: `accept()` MUST run before any `close(code=...)`
    # call. Per the ASGI websocket spec, a server that sends
    # `websocket.close` as its *first* outgoing message (i.e. before
    # `websocket.accept`) never completes the opening HTTP Upgrade
    # handshake at all — uvicorn rejects the connection at the HTTP level
    # instead of performing a WebSocket closing handshake, so the numeric
    # close code (4429/4401 below) never reaches the client. Every real
    # browser's native WebSocket implementation reports that as
    # `CloseEvent{code: 1006, wasClean: false}` — "abnormal closure" — not
    # the app-specific code the server actually intended (this codebase's
    # own `docs/realtime/02-websocket-guide.md` had documented the old,
    # broken "closes with 4429/4401 before accepting" order as if it were
    # correct). Starlette's in-process `TestClient.websocket_connect`
    # doesn't reproduce this — its `WebSocketTestSession` simulates the
    # ASGI protocol directly and hands back whatever code the app sent
    # regardless of accept order, which is why `test_ep19_1.py`'s
    # rate-limit/auth-failure tests passed even with the bug. Accepting
    # first (and immediately closing with the real code on failure) is the
    # standard fix for "deliver a custom WebSocket close code to a real
    # browser" — see docs/realtime/02-websocket-guide.md, updated in
    # lockstep with this fix.
    await websocket.accept()

    if not await container.realtime_rate_limiter.check(ip=ip):
        await websocket.close(code=4429, reason="Too many connection attempts")
        return

    try:
        raw_token = extract_token(
            authorization_header=websocket.headers.get("authorization"), query_token=token
        )
        principal = await authenticate_realtime_connection(
            session_factory=container.session_factory,
            token=raw_token,
            organization_id=organization_id,
            settings=container.settings,
        )
    except RealtimeAuthError as exc:
        await websocket.close(code=4401, reason=exc.message)
        return

    connection_manager = container.connection_manager
    reconnect_count = 1 if websocket.query_params.get("reconnect") else 0
    if reconnect_count:
        reconnects_total.labels(kind=ConnectionKind.WEBSOCKET.value).inc()
    info = connection_manager.register(
        organization_id=principal.organization_id,
        kind=ConnectionKind.WEBSOCKET,
        principal_kind=principal.kind,
        principal_id=principal.principal_id,
        reconnect_count=reconnect_count,
    )
    log.info(
        "realtime_ws_connected",
        connection_id=info.connection_id,
        organization_id=str(principal.organization_id),
    )

    # EP-19.4 — root-caused production regression: "Connection closed
    # (1006)", growing reconnect counts, heartbeat latency stuck at "—".
    #
    # Two confirmed defects, verified directly against Starlette/uvicorn
    # source (not guessed):
    #
    # 1. No write serialization. `starlette.websockets.WebSocket.send()`
    #    has no internal lock — it only inspects `application_state`
    #    (confirmed by reading starlette/websockets.py). `_forward_events`
    #    and `_heartbeat_and_read` are two independent tasks that both call
    #    `websocket.send_*()`/`close()` on the SAME socket with zero
    #    synchronization. The reachable failure: `_heartbeat_and_read`
    #    times out and calls `close(4408)`, which flips
    #    `application_state` to DISCONNECTED *before* the close frame is
    #    even written; if `_forward_events` is mid-flight sending a queued
    #    event at that moment, its `send_text()` raises
    #    `RuntimeError('Cannot call "send" once a close message has been
    #    sent.')`.
    #
    # 2. No close-on-every-path. That RuntimeError (and any other
    #    exception from either task — a serialization error, a client
    #    disconnect surfacing as `WebSocketDisconnect` from the heartbeat
    #    task's read, etc.) used to just make the task's `asyncio.wait()`
    #    return; the handler logged it and returned WITHOUT ever calling
    #    `websocket.close()`. Per uvicorn's `run_asgi()`
    #    (uvicorn/protocols/websockets/websockets_impl.py): when the ASGI
    #    app coroutine returns having never sent a `"websocket.close"`
    #    message, uvicorn falls back to `self.transport.close()` — a raw
    #    TCP close with NO WebSocket closing handshake. That is *exactly*
    #    what a browser reports as `CloseEvent{code: 1006, wasClean:
    #    false}`, with no code/reason ever delivered — matching every
    #    reported symptom precisely, including the client-side heartbeat
    #    UI showing "—" (the connection died before any diagnosable frame
    #    reached it).
    #
    # This has been present, unchanged, since the very first EP-19.1
    # commit (`git log -- app/api/v1/realtime.py`) — EP-24.6.1's earlier
    # hotfix fixed a different bug (accept()-before-close ordering for the
    # two *rejection* paths above) and never touched this gap in the
    # steady-state task loop. Fix: (a) one `asyncio.Lock` serializes every
    # outbound frame across both tasks, eliminating the send-after-close
    # race at its source; (b) a single `_close_gracefully()` helper is the
    # only place that ever calls `websocket.close()`, and it is now always
    # invoked before this handler returns, regardless of which task
    # completed or why — so uvicorn's "app returned without closing"
    # fallback can never fire again for a healthy connection.
    write_lock = asyncio.Lock()

    async def _close_gracefully(*, code: int, reason: str) -> None:
        """The one call site that ever sends `websocket.close()`. Always
        holds `write_lock` and always re-checks `application_state` first,
        so calling this after the socket is already disconnected (client
        dropped, or the other task already closed it) is a safe no-op
        instead of a redundant close message or an uncaught RuntimeError.

        `client_state` (did WE receive a disconnect) and `application_state`
        (did WE send a close) are tracked separately by Starlette — a
        client-initiated disconnect only flips `client_state`, so this
        function still attempts a close in that case (correct — completing
        the closing handshake is normally the server's job). If the
        underlying transport is already dead by then, Starlette's own
        `send()` converts the resulting `OSError` into
        `WebSocketDisconnect(code=1006)` and raises it — caught here too,
        for the same reason as `RuntimeError`: this helper must NEVER let a
        best-effort close attempt itself become a new uncaught exception
        that skips the explicit close this whole fix exists to guarantee."""
        async with write_lock:
            if websocket.application_state != WebSocketState.CONNECTED:
                return
            try:
                await websocket.close(code=code, reason=reason)
            except (RuntimeError, WebSocketDisconnect):
                # Belt-and-suspenders: the lock already rules out a race
                # with our own writers — this only guards Starlette's state
                # machine disagreeing with a transport that dropped at the
                # OS level between our check and the close() call.
                pass
        log.info(
            "realtime_ws_closed",
            connection_id=info.connection_id,
            organization_id=str(principal.organization_id),
            close_code=code,
            close_reason=reason,
        )

    async def _forward_events() -> None:
        async for event in connection_manager.receive(info.connection_id):
            async with write_lock:
                if websocket.application_state != WebSocketState.CONNECTED:
                    return
                await websocket.send_text(event.model_dump_json())
            log.debug(
                "realtime_ws_event_forwarded",
                connection_id=info.connection_id,
                event_type=event.type.value,
            )

    async def _heartbeat_and_read() -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
            async with write_lock:
                if websocket.application_state != WebSocketState.CONNECTED:
                    return
                await websocket.send_json({"type": "ping"})
            log.debug("realtime_ws_heartbeat_sent", connection_id=info.connection_id)
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=HEARTBEAT_TIMEOUT_SECONDS)
                log.debug("realtime_ws_heartbeat_pong_received", connection_id=info.connection_id)
            except TimeoutError:
                connection_manager.record_heartbeat_failure(info.connection_id)
                heartbeat_failures_total.inc()
                log.info(
                    "realtime_ws_heartbeat_timeout",
                    connection_id=info.connection_id,
                    organization_id=str(principal.organization_id),
                )
                await _close_gracefully(code=4408, reason="Heartbeat timeout")
                return

    forward_task = asyncio.create_task(_forward_events())
    heartbeat_task = asyncio.create_task(_heartbeat_and_read())

    try:
        done, pending = await asyncio.wait(
            {forward_task, heartbeat_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()

        close_code, close_reason = 1000, "Connection ended"
        for task in done:
            try:
                task_exc = task.exception()
            except asyncio.CancelledError:
                continue
            if task_exc is None:
                continue
            if isinstance(task_exc, WebSocketDisconnect):
                # Client-initiated disconnect — application_state already
                # reflects this, so the close below is a correct no-op.
                close_code, close_reason = task_exc.code or 1000, "Client disconnected"
                continue
            log.warning(
                "realtime_ws_task_failed",
                connection_id=info.connection_id,
                organization_id=str(principal.organization_id),
                reason=str(task_exc),
                exc_type=type(task_exc).__name__,
            )
            close_code, close_reason = 1011, "Internal error"

        # The fix's core guarantee: ALWAYS attempt an explicit close before
        # this handler returns, no matter which branch above ran — see the
        # docstring-length comment above `write_lock` for exactly why this
        # is what actually prevents the 1006 regression.
        await _close_gracefully(code=close_code, reason=close_reason)
    finally:
        forward_task.cancel()
        heartbeat_task.cancel()
        connection_manager.unregister(info.connection_id)


@router.get("/events")
async def sse_events(
    request: Request,
    token: str | None = Query(default=None),
    organization_id: uuid.UUID | None = Query(default=None),
) -> StreamingResponse:
    container: AppContainer = request.app.state.container
    ip = request.client.host if request.client else None

    if not await container.realtime_rate_limiter.check(ip=ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many connection attempts",
        )

    try:
        raw_token = extract_token(
            authorization_header=request.headers.get("authorization"), query_token=token
        )
        principal = await authenticate_realtime_connection(
            session_factory=container.session_factory,
            token=raw_token,
            organization_id=organization_id,
            settings=container.settings,
        )
    except RealtimeAuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=exc.message) from exc

    connection_manager = container.connection_manager
    last_event_id_header = request.headers.get("last-event-id")
    reconnect_count = 1 if last_event_id_header else 0
    if reconnect_count:
        reconnects_total.labels(kind=ConnectionKind.SSE.value).inc()

    last_event_id: uuid.UUID | None = None
    if last_event_id_header:
        try:
            last_event_id = uuid.UUID(last_event_id_header)
        except ValueError:
            last_event_id = None

    info = connection_manager.register(
        organization_id=principal.organization_id,
        kind=ConnectionKind.SSE,
        principal_kind=principal.kind,
        principal_id=principal.principal_id,
        reconnect_count=reconnect_count,
    )
    log.info(
        "realtime_sse_connected",
        connection_id=info.connection_id,
        organization_id=str(principal.organization_id),
    )

    async def event_stream() -> AsyncIterator[bytes]:
        try:
            if last_event_id is not None:
                for replayed in await container.event_bus.replay_since(
                    principal.organization_id, last_event_id
                ):
                    yield _format_sse(replayed)

            events = connection_manager.receive(info.connection_id)
            while True:
                try:
                    event = await asyncio.wait_for(
                        events.__anext__(), timeout=HEARTBEAT_INTERVAL_SECONDS
                    )
                except TimeoutError:
                    yield b": heartbeat\n\n"
                    continue
                except StopAsyncIteration:
                    return
                yield _format_sse(event)
        finally:
            connection_manager.unregister(info.connection_id)

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=headers)
