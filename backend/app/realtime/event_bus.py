"""Redis-backed event bus — EP-19.1.

Publishes `RealtimeEvent`s onto a per-organization Redis Pub/Sub channel
(`realtime:org:<uuid>`) and maintains a small, bounded replay buffer per
organization (a capped Redis list) so an SSE client that reconnects with
`Last-Event-ID` can catch up on whatever it missed, without this backend
needing to persist events anywhere durable — Redis is already a first-class
dependency (`app.core.redis`), reused here rather than adding a new message
queue.

Dispatch is a single process-wide Redis `PSUBSCRIBE realtime:org:*` — one
subscription per backend replica, not one per connected client — fed to
`ConnectionManager`, which fans each event out to that org's local
WebSocket/SSE connections. This keeps Redis subscription count bounded by
the number of API replicas, not the number of connected browser tabs.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import structlog
from redis.asyncio import Redis

from app.realtime.events import ORG_CHANNEL_PATTERN, RealtimeEvent, org_channel, org_id_from_channel

log = structlog.get_logger(__name__)

DEFAULT_REPLAY_BUFFER_SIZE = 200
DEFAULT_REPLAY_TTL_SECONDS = 3600


class EventBus:
    """Publishes events and replays recent history for one Redis instance.

    Stateless apart from the shared Redis client — safe to construct one
    per request (cheap) or hold a single instance for the process lifetime
    (also fine); `ConnectionManager` holds one.
    """

    def __init__(
        self,
        redis: Redis[Any],
        *,
        replay_buffer_size: int = DEFAULT_REPLAY_BUFFER_SIZE,
        replay_ttl_seconds: int = DEFAULT_REPLAY_TTL_SECONDS,
    ) -> None:
        self._redis = redis
        self._replay_buffer_size = replay_buffer_size
        self._replay_ttl_seconds = replay_ttl_seconds

    @staticmethod
    def _replay_key(organization_id: uuid.UUID) -> str:
        return f"realtime:replay:{organization_id}"

    async def publish(self, event: RealtimeEvent) -> None:
        """Publish `event` to its organization's channel and append it to
        that organization's replay buffer. Never raises on a Redis error —
        a dropped real-time event must never fail (or roll back) the
        request that produced it; callers that need to know whether the
        publish succeeded should wrap this themselves. See
        `docs/backend/REALTIME_ARCHITECTURE.md`'s "never block ingestion"
        section."""
        data = event.model_dump_json()
        channel = event.channel()
        try:
            pipe = self._redis.pipeline()
            pipe.publish(channel, data)
            key = self._replay_key(event.organization_id)
            pipe.rpush(key, data)
            pipe.ltrim(key, -self._replay_buffer_size, -1)
            pipe.expire(key, self._replay_ttl_seconds)
            await pipe.execute()
        except Exception:
            log.warning(
                "realtime_publish_failed",
                organization_id=str(event.organization_id),
                event_type=event.type.value,
                exc_info=True,
            )

    async def replay_since(
        self,
        organization_id: uuid.UUID,
        last_event_id: uuid.UUID | None,
    ) -> list[RealtimeEvent]:
        """Events published after `last_event_id`, for SSE reconnect via
        `Last-Event-ID`. Returns everything currently buffered (bounded by
        `replay_buffer_size`) if `last_event_id` is None, unknown (the
        buffer rotated past it), or not found. Never raises — a replay
        failure degrades to "no history", not a broken connection."""
        try:
            raw_events = await self._redis.lrange(self._replay_key(organization_id), 0, -1)
        except Exception:
            log.warning(
                "realtime_replay_failed", organization_id=str(organization_id), exc_info=True
            )
            return []

        events: list[RealtimeEvent] = []
        for raw in raw_events:
            text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            try:
                events.append(RealtimeEvent.model_validate_json(text))
            except ValueError:
                continue

        if last_event_id is None:
            return events
        for index, event in enumerate(events):
            if event.event_id == last_event_id:
                return events[index + 1 :]
        return events

    async def subscribe_all_organizations(
        self,
    ) -> AsyncIterator[tuple[uuid.UUID, RealtimeEvent]]:
        """Yields `(organization_id, event)` for every event published to
        any organization's channel — the single process-wide subscription
        `ConnectionManager` drives its local dispatch loop from. Malformed
        channel names or payloads are skipped, never raised, since one bad
        message must never kill the whole dispatch loop for every other
        organization sharing this subscription."""
        pubsub = self._redis.pubsub()
        await pubsub.psubscribe(ORG_CHANNEL_PATTERN)
        try:
            async for message in pubsub.listen():
                if message["type"] != "pmessage":
                    continue
                channel = message["channel"]
                if isinstance(channel, bytes):
                    channel = channel.decode("utf-8")
                organization_id = org_id_from_channel(channel)
                if organization_id is None:
                    continue
                data = message["data"]
                text = data.decode("utf-8") if isinstance(data, bytes) else data
                try:
                    event = RealtimeEvent.model_validate_json(text)
                except ValueError:
                    log.warning("realtime_malformed_event", channel=channel)
                    continue
                yield organization_id, event
        finally:
            await pubsub.punsubscribe(ORG_CHANNEL_PATTERN)
            await pubsub.aclose()


__all__ = ["EventBus", "org_channel"]
