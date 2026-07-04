"""Connection + subscription manager — EP-19.1.

One `ConnectionManager` per process (held on `AppContainer`, alongside the
existing `redis`/`session_factory`), owning:

  - the process-wide `EventBus.subscribe_all_organizations()` dispatch loop
    (started once, in the app lifespan)
  - an in-memory, organization-scoped registry of every locally-connected
    WebSocket or SSE client — "subscription manager" and "connection
    manager" are the same object here: a connection *is* a subscription to
    its organization's event stream, there is no separate topic model to
    subscribe/unsubscribe within an organization (every event type flows
    to every connection for that org; client-side filtering by `type` is
    expected, matching the ticket's flat event-type list rather than a
    per-type subscription API)

Multiple browser tabs, multiple users, multiple devices, and SDK
connections are all just independent entries in the same per-org set —
nothing here assumes at most one connection per user.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import defaultdict
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from enum import StrEnum

import structlog

from app.realtime.auth import PrincipalKind
from app.realtime.event_bus import EventBus
from app.realtime.events import RealtimeEvent

log = structlog.get_logger(__name__)

DEFAULT_QUEUE_MAXSIZE = 256


class ConnectionKind(StrEnum):
    WEBSOCKET = "websocket"
    SSE = "sse"


@dataclass
class ConnectionInfo:
    """Everything tracked about one locally-connected client, for both
    dispatch (the queue) and the "Connection Management" success criteria
    (duration, reconnect count, heartbeat failures)."""

    connection_id: str
    organization_id: uuid.UUID
    kind: ConnectionKind
    principal_kind: PrincipalKind
    principal_id: uuid.UUID
    connected_at: float = field(default_factory=time.monotonic)
    reconnect_count: int = 0
    heartbeat_failures: int = 0
    queue: asyncio.Queue[RealtimeEvent] = field(
        default_factory=lambda: asyncio.Queue(maxsize=DEFAULT_QUEUE_MAXSIZE)
    )

    @property
    def duration_seconds(self) -> float:
        return time.monotonic() - self.connected_at


class ConnectionManager:
    """Registers/unregisters connections and dispatches events to them.

    Dispatch is deliberately non-blocking end to end: `dispatch` (called
    from the single Redis-fed loop in `run_dispatch_loop`) uses
    `Queue.put_nowait` for every connection in the target organization —
    if a connection's queue is full (a slow/stalled client not draining
    fast enough), that one event is dropped for that one connection and a
    `dropped_events_total` metric increments; the queue-full connection
    never blocks delivery to every other connection, and a slow client is
    the one that loses events, not the ingestion path or any other
    client's stream.
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._connections: dict[str, ConnectionInfo] = {}
        self._by_org: dict[uuid.UUID, set[str]] = defaultdict(set)
        self._dispatch_task: asyncio.Task[None] | None = None
        self._on_drop: list[Callable[[ConnectionInfo], None]] = []
        self._on_dispatch: list[Callable[[ConnectionInfo, RealtimeEvent], None]] = []

    # ── Lifecycle ────────────────────────────────────────────────────────

    def start(self) -> None:
        """Starts the process-wide dispatch loop. Idempotent — safe to call
        more than once (e.g. across test app rebuilds); only the first call
        in a given event loop actually spawns the task."""
        if self._dispatch_task is not None and not self._dispatch_task.done():
            return
        self._dispatch_task = asyncio.create_task(self._run_dispatch_loop())

    async def stop(self) -> None:
        if self._dispatch_task is None:
            return
        self._dispatch_task.cancel()
        try:
            await self._dispatch_task
        except asyncio.CancelledError:
            pass
        except Exception:
            log.warning("realtime_dispatch_loop_stop_error", exc_info=True)
        self._dispatch_task = None

    async def _run_dispatch_loop(self) -> None:
        try:
            async for organization_id, event in self._event_bus.subscribe_all_organizations():
                self.dispatch(organization_id, event)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.error("realtime_dispatch_loop_crashed", exc_info=True)

    # ── Registration ─────────────────────────────────────────────────────

    def register(
        self,
        *,
        organization_id: uuid.UUID,
        kind: ConnectionKind,
        principal_kind: PrincipalKind,
        principal_id: uuid.UUID,
        reconnect_count: int = 0,
    ) -> ConnectionInfo:
        info = ConnectionInfo(
            connection_id=str(uuid.uuid4()),
            organization_id=organization_id,
            kind=kind,
            principal_kind=principal_kind,
            principal_id=principal_id,
            reconnect_count=reconnect_count,
        )
        self._connections[info.connection_id] = info
        self._by_org[organization_id].add(info.connection_id)
        log.info(
            "realtime_connection_registered",
            connection_id=info.connection_id,
            organization_id=str(organization_id),
            kind=kind.value,
        )
        return info

    def unregister(self, connection_id: str) -> ConnectionInfo | None:
        info = self._connections.pop(connection_id, None)
        if info is None:
            return None
        org_set = self._by_org.get(info.organization_id)
        if org_set is not None:
            org_set.discard(connection_id)
            if not org_set:
                del self._by_org[info.organization_id]
        log.info(
            "realtime_connection_unregistered",
            connection_id=connection_id,
            organization_id=str(info.organization_id),
            duration_seconds=round(info.duration_seconds, 3),
            heartbeat_failures=info.heartbeat_failures,
        )
        return info

    # ── Dispatch ──────────────────────────────────────────────────────────

    def dispatch(self, organization_id: uuid.UUID, event: RealtimeEvent) -> None:
        """Fan `event` out to every locally-connected client for
        `organization_id`. Never awaits, never raises — called from the
        single dispatch loop and must not stall it."""
        for connection_id in self._by_org.get(organization_id, ()):
            info = self._connections.get(connection_id)
            if info is None:
                continue
            try:
                info.queue.put_nowait(event)
            except asyncio.QueueFull:
                for drop_callback in self._on_drop:
                    drop_callback(info)
                log.warning(
                    "realtime_event_dropped_queue_full",
                    connection_id=connection_id,
                    organization_id=str(organization_id),
                )
            else:
                for dispatch_callback in self._on_dispatch:
                    dispatch_callback(info, event)

    def on_drop(self, callback: Callable[[ConnectionInfo], None]) -> None:
        """Registers a callback invoked whenever an event is dropped for a
        full connection queue — used by `metrics.py` to increment
        `dropped_events_total` without this module importing Prometheus
        directly."""
        self._on_drop.append(callback)

    def on_dispatch(self, callback: Callable[[ConnectionInfo, RealtimeEvent], None]) -> None:
        """Registers a callback invoked whenever an event is successfully
        queued for a connection — used by `metrics.py` for
        `events_dispatched_total`/dispatch-latency."""
        self._on_dispatch.append(callback)

    # ── Introspection (Connection Management success criteria) ──────────

    def connection_count(self, organization_id: uuid.UUID | None = None) -> int:
        if organization_id is None:
            return len(self._connections)
        return len(self._by_org.get(organization_id, ()))

    def connections_for_org(self, organization_id: uuid.UUID) -> list[ConnectionInfo]:
        return [
            self._connections[cid]
            for cid in self._by_org.get(organization_id, ())
            if cid in self._connections
        ]

    def record_heartbeat_failure(self, connection_id: str) -> None:
        info = self._connections.get(connection_id)
        if info is not None:
            info.heartbeat_failures += 1

    async def receive(self, connection_id: str) -> AsyncIterator[RealtimeEvent]:
        """Async-iterates events queued for `connection_id` until the
        connection is unregistered."""
        info = self._connections.get(connection_id)
        if info is None:
            return
        while connection_id in self._connections:
            try:
                event = await asyncio.wait_for(info.queue.get(), timeout=1.0)
            except TimeoutError:
                continue
            yield event
