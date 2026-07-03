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

    await websocket.accept()

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

    async def _forward_events() -> None:
        async for event in connection_manager.receive(info.connection_id):
            await websocket.send_text(event.model_dump_json())

    async def _heartbeat_and_read() -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
            await websocket.send_json({"type": "ping"})
            try:
                await asyncio.wait_for(
                    websocket.receive_text(), timeout=HEARTBEAT_TIMEOUT_SECONDS
                )
            except TimeoutError:
                connection_manager.record_heartbeat_failure(info.connection_id)
                heartbeat_failures_total.inc()
                await websocket.close(code=4408, reason="Heartbeat timeout")
                return

    forward_task = asyncio.create_task(_forward_events())
    heartbeat_task = asyncio.create_task(_heartbeat_and_read())

    try:
        done, pending = await asyncio.wait(
            {forward_task, heartbeat_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        for task in done:
            if task.exception() and not isinstance(task.exception(), WebSocketDisconnect):
                exc = task.exception()
                if exc is not None and not isinstance(exc, asyncio.CancelledError):
                    log.info(
                        "realtime_ws_closed",
                        connection_id=info.connection_id,
                        reason=str(exc),
                    )
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
