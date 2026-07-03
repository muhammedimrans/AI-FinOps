"""
Costorah — the SDK's public entry point.

    from costorah import Costorah

    client = Costorah(api_key="costorah_live_xxxxxxxxx")
    client.track(
        provider="openai",
        model="gpt-4.1",
        input_tokens=500,
        output_tokens=220,
        cost=0.041,
        latency_ms=621,
    )

Thread safety: a single `Costorah` instance is safe to share across
threads.

EP-18.3 reliability layer: `track()` validates its arguments synchronously
(cheap, no I/O) and then hands the built payload to a background worker —
it never makes a blocking network call itself, and returns in well under a
millisecond. See `sdk/docs/RELIABILITY.md` for the full pipeline (memory
queue -> background worker -> persistent queue -> compression -> retry ->
circuit breaker -> connection pool) and for what this means for
`TrackResult` (it can no longer carry the server-assigned `usage_id`/
`processed_at`/`duplicate` fields synchronously — those are only known
once the event is actually delivered, which now happens off the critical
path). `client.flush()` / `client.shutdown()` block until pending events
are delivered when a caller needs that guarantee (e.g. before process
exit, or in a test).
"""

from __future__ import annotations

import hashlib
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from costorah._logging import get_logger
from costorah._util import generate_request_id
from costorah.config import Config
from costorah.exceptions import ValidationError
from costorah.reliability import BackgroundWorker, ConnectionPool, HealthMonitor, QueuedEvent
from costorah.types import SUPPORTED_PROVIDERS, UsageStatus

_log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class TrackResult:
    """Result of a `track()` call. `queued` is always True on a
    successful call (validation passed, the event was accepted into the
    reliability pipeline) — it does NOT mean the event has reached
    COSTORAH yet. `usage_id`/`processed_at`/`duplicate` are only known
    once delivery actually completes, which happens asynchronously in the
    background; they are `None`/`False` here. Use `client.flush()` if a
    caller needs to wait for actual delivery."""

    success: bool
    request_id: str
    queued: bool = True
    usage_id: str | None = None
    processed_at: str | None = None
    duplicate: bool = False


class Costorah:
    """The COSTORAH SDK client."""

    def __init__(
        self,
        api_key: str,
        *,
        endpoint: str = "https://api.costorah.com",
        timeout: float = 30.0,
        batch_size: int = 25,
        flush_interval: float = 5.0,
        max_retries: int = 3,
        verify_tls: bool = True,
        queue_size: int = 10_000,
        overflow_policy: str = "drop_oldest",
        persistent_queue: bool = False,
        compression: bool = True,
        retry: bool = True,
        _transport: Any | None = None,
    ) -> None:
        self.config = Config(
            api_key=api_key,
            endpoint=endpoint,
            timeout=timeout,
            batch_size=batch_size,
            flush_interval=flush_interval,
            max_retries=max_retries,
            verify_tls=verify_tls,
            queue_size=queue_size,
            overflow_policy=overflow_policy,
            persistent_queue=persistent_queue,
            compression=compression,
            retry=retry,
        )
        pool = ConnectionPool(self.config, transport=_transport)
        self._worker = BackgroundWorker(
            self.config,
            queue_size=self.config.queue_size,
            overflow_policy=self.config.overflow_policy,
            persistent_queue_path=_persistent_queue_path(self.config),
            compression_enabled=self.config.compression,
            retry_enabled=self.config.retry,
            poll_interval=min(self.config.flush_interval, 0.5),
            connection_pool=pool,
        )
        self._health = HealthMonitor(self._worker)
        self._worker.start()

    def track(
        self,
        *,
        provider: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cached_tokens: int | None = None,
        total_tokens: int | None = None,
        cost: float = 0.0,
        currency: str = "USD",
        latency_ms: int | None = None,
        status: UsageStatus = "success",
        region: str | None = None,
        project_id: str | None = None,
        request_id: str | None = None,
        timestamp: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TrackResult:
        """Report one usage event. Validates its arguments synchronously
        (raising a `costorah.*` exception immediately on bad input, same
        as before) and then hands the payload to the background delivery
        pipeline — this method does not make a network call and returns
        immediately. See `TrackResult`'s docstring and
        `sdk/docs/RELIABILITY.md` for what "queued" means here."""
        payload = self._build_payload(
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            total_tokens=total_tokens,
            cost=cost,
            currency=currency,
            latency_ms=latency_ms,
            status=status,
            region=region,
            project_id=project_id,
            request_id=request_id,
            timestamp=timestamp,
            metadata=metadata,
        )
        request_id_str = str(payload["request_id"])
        queued = self._worker.submit(QueuedEvent(payload=payload))
        if not queued:
            _log.warning(
                "costorah: event dropped, queue full (overflow_policy=%s) request_id=%s",
                self.config.overflow_policy,
                request_id_str,
            )
        return TrackResult(success=queued, request_id=request_id_str, queued=queued)

    def flush(self, timeout: float = 10.0) -> bool:
        """Blocks until every queued event has been delivered (or
        permanently dropped), or `timeout` elapses. Returns True if the
        queue fully drained. Does not stop the background worker —
        `track()` remains usable immediately afterward."""
        return self._worker.flush(timeout=timeout)

    def shutdown(self, timeout: float = 10.0) -> None:
        """Graceful shutdown: flush pending events (best-effort, bounded
        by `timeout`), then stop the background worker. Safe to call more
        than once. `track()` after `shutdown()` still enqueues locally but
        will not be delivered until a new client is constructed."""
        self._worker.shutdown(timeout=timeout)

    def health(self) -> dict[str, Any]:
        """Matches the ticket's literal shape:
        `{"worker": "running", "queue_depth": 24, "retry_queue": 3,
        "circuit": "closed", "compression": "enabled"}`."""
        return self._health.snapshot()

    def queue_stats(self) -> dict[str, Any]:
        """Queue depth, dropped events, retry queue size, worker status,
        and the TelemetryMetrics snapshot (sent/failed totals, retry
        count, average upload latency, compression ratio, last batch
        size, worker uptime)."""
        return self._health.queue_stats()

    def _build_payload(
        self,
        *,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int | None,
        total_tokens: int | None,
        cost: float,
        currency: str,
        latency_ms: int | None,
        status: UsageStatus,
        region: str | None,
        project_id: str | None,
        request_id: str | None,
        timestamp: datetime | None,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        normalized_provider = provider.strip().lower()
        if normalized_provider not in SUPPORTED_PROVIDERS:
            raise ValidationError(
                f"Unsupported provider {provider!r}. Must be one of: {sorted(SUPPORTED_PROVIDERS)}"
            )
        if not model or not model.strip():
            raise ValidationError("model must not be blank")
        if input_tokens < 0 or output_tokens < 0:
            raise ValidationError("input_tokens and output_tokens must be >= 0")
        if cost < 0:
            raise ValidationError("cost must be >= 0")
        if cached_tokens is not None and cached_tokens > input_tokens:
            raise ValidationError("cached_tokens must not exceed input_tokens")
        if total_tokens is not None and total_tokens != input_tokens + output_tokens:
            raise ValidationError(
                f"total_tokens ({total_tokens}) must equal "
                f"input_tokens + output_tokens ({input_tokens + output_tokens})"
            )

        payload: dict[str, Any] = {
            "provider": normalized_provider,
            "model": model.strip(),
            "request_id": request_id or generate_request_id(),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost": cost,
            "currency": currency,
            "status": status,
            "metadata": metadata or {},
        }
        if cached_tokens is not None:
            payload["cached_tokens"] = cached_tokens
        if total_tokens is not None:
            payload["total_tokens"] = total_tokens
        if latency_ms is not None:
            payload["latency_ms"] = latency_ms
        if region is not None:
            payload["region"] = region
        if project_id is not None:
            payload["project_id"] = project_id
        if timestamp is not None:
            payload["timestamp"] = timestamp.isoformat()
        return payload

    def close(self) -> None:
        """Alias for `shutdown()` — flushes pending events and stops the
        background worker. Safe to call more than once."""
        self.shutdown()

    def __enter__(self) -> Costorah:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


def _persistent_queue_path(config: Config) -> str:
    """A real on-disk SQLite file, namespaced by API key, when
    `persistent_queue=True` (crash-durable, and reused across restarts
    with the same key so recovery actually has something to recover); an
    in-memory database otherwise (same queue/retry mechanics, just not
    durable across a process restart)."""
    if not config.persistent_queue:
        return ":memory:"
    key_hash = hashlib.sha256(config.api_key.encode()).hexdigest()[:16]
    path = Path(tempfile.gettempdir()) / "costorah" / f"queue-{key_hash}.db"
    return str(path)
