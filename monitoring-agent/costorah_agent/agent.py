"""
Agent — the core orchestrator tying every subsystem together.

Lifecycle: read configuration -> resolve/authenticate the API key ->
build enabled collectors -> run the collection loop (poll each collector
every `collection.interval_seconds`, normalize, enqueue) concurrently with
the delivery loop (drain the queue, send, retry) -> graceful shutdown on
SIGTERM/SIGINT (stop accepting new work, flush what's already queued as
far as possible, close all HTTP clients and the SQLite store cleanly).

No provider-specific logic lives here — collectors are opaque
BaseCollector instances built by the CollectorRegistry (see
collectors/registry.py); this module only ever calls the four lifecycle
methods every collector implements.
"""

from __future__ import annotations

import asyncio
import signal
from datetime import UTC, datetime
from typing import Any

import structlog

from costorah_agent.collectors.base import BaseCollector, CollectorError
from costorah_agent.collectors.models import CollectorHealth
from costorah_agent.collectors.registry import CollectorRegistry, get_default_registry
from costorah_agent.config import AgentConfig
from costorah_agent.queue.memory_queue import EventQueue
from costorah_agent.queue.retry import RetryPolicy
from costorah_agent.queue.sqlite_store import SQLiteEventStore
from costorah_agent.transport.http_client import HttpClient
from costorah_agent.transport.sender import Sender

log = structlog.get_logger(__name__)


class AgentAuthenticationError(Exception):
    """Raised when the agent cannot resolve a usable organization API key."""


class Agent:
    """The COSTORAH Monitoring Agent's runtime."""

    def __init__(
        self,
        config: AgentConfig,
        *,
        registry: CollectorRegistry | None = None,
        http_client: HttpClient | None = None,
    ) -> None:
        self.config = config
        self._registry = registry or get_default_registry()
        self._collectors: dict[str, BaseCollector] = {}
        self._started_at: datetime | None = None
        self._stop_event = asyncio.Event()
        self._tasks: list[asyncio.Task[None]] = []

        self._store = SQLiteEventStore(config.queue.sqlite_path)
        self._queue = EventQueue(config.queue.max_memory_events, self._store)

        api_key = self._resolve_api_key()
        self._http_client = http_client or HttpClient(
            endpoint=config.server.endpoint,
            api_key=api_key,
            timeout_seconds=config.server.timeout_seconds,
            verify_tls=config.server.verify_tls,
        )
        self._sender = Sender(
            queue=self._queue,
            store=self._store,
            http_client=self._http_client,
            retry_policy=RetryPolicy(
                backoff_seconds=config.retry.backoff_seconds,
                max_attempts=config.retry.max_attempts,
            ),
            batch_size=config.collection.batch_size,
        )

    def _resolve_api_key(self) -> str:
        if self.config.organization.api_key:
            return self.config.organization.api_key
        raise AgentAuthenticationError(
            "No organization API key configured. Set organization.api_key in "
            "config.yaml, or the COSTORAH_AGENT_ORGANIZATION__API_KEY "
            "environment variable, or run `costorah-agent config set-key`."
        )

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def start(self) -> None:
        self._started_at = datetime.now(UTC)
        self._collectors = self._registry.build_enabled(
            self.config.enabled_providers(), self._provider_configs()
        )
        log.info(
            "agent_started",
            collectors=sorted(self._collectors),
            interval_seconds=self.config.collection.interval_seconds,
            endpoint=self.config.server.endpoint,
        )

        self._install_signal_handlers()
        self._tasks = [
            asyncio.create_task(self._collection_loop(), name="collection_loop"),
            asyncio.create_task(self._delivery_loop(), name="delivery_loop"),
        ]

    async def run_forever(self) -> None:
        """Block until a stop is requested, then shut down.

        Callers must call `start()` themselves first (the CLI does this so
        it can start the health/metrics HTTP server in between — see
        cli.py's `_run_agent`). This deliberately does *not* call start()
        itself to avoid double-starting the collection/delivery loops.
        """
        await self._stop_event.wait()
        await self.shutdown()

    def request_stop(self) -> None:
        self._stop_event.set()

    async def shutdown(self) -> None:
        log.info("agent_shutting_down")
        self._stop_event.set()
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Best-effort final flush so anything already in memory doesn't
        # need a full retry cycle after restart.
        try:
            await self._sender.run_once()
        except Exception:  # shutdown must not hang on a delivery error
            log.warning("final_flush_failed", exc_info=True)

        for collector in self._collectors.values():
            await collector.shutdown()
        await self._http_client.close()
        await self._store.close()
        log.info("agent_stopped")

    def _install_signal_handlers(self) -> None:
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, self.request_stop)
            except NotImplementedError:
                # Windows: add_signal_handler is unsupported for SIGTERM.
                # The CLI falls back to handling KeyboardInterrupt instead.
                pass

    # ── Loops ────────────────────────────────────────────────────────────────

    async def _collection_loop(self) -> None:
        interval = self.config.collection.interval_seconds
        while not self._stop_event.is_set():
            await self._collect_once()
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
            except TimeoutError:
                pass  # normal: interval elapsed, loop again

    async def _collect_once(self) -> None:
        for name, collector in self._collectors.items():
            try:
                events = await collector.collect()
            except CollectorError as exc:
                log.warning("collector_poll_failed", collector=name, error=str(exc))
                continue
            except Exception:  # one bad collector must not stop the others
                log.exception("collector_poll_crashed", collector=name)
                continue

            for event in events:
                await self._queue.put(event.request_id, event.to_ingestion_payload())

    async def _delivery_loop(self) -> None:
        # Deliver more often than we collect, so the queue doesn't build up
        # between polls under normal (non-degraded) network conditions.
        delivery_interval = min(self.config.collection.interval_seconds, 5.0)
        while not self._stop_event.is_set():
            try:
                await self._sender.run_once()
            except Exception:  # delivery loop must survive transient errors
                log.exception("delivery_loop_error")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=delivery_interval)
            except TimeoutError:
                pass

    # ── Introspection (for CLI / health / metrics) ──────────────────────────

    def _provider_configs(self) -> dict[str, dict[str, Any]]:
        # Per-provider config sub-sections aren't in the top-level schema
        # yet (EP-17 ships env-var-driven credentials — see each
        # collector's docstring); reserved for a future config.yaml
        # extension without a breaking change.
        return {}

    async def collector_health(self) -> list[CollectorHealth]:
        return [await c.health() for c in self._collectors.values()]

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

    @property
    def started_at(self) -> datetime | None:
        return self._started_at

    @property
    def sender(self) -> Sender:
        return self._sender

    @property
    def store(self) -> SQLiteEventStore:
        return self._store
