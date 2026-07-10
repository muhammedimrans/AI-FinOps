"""UsageSyncScheduler — Background Usage Synchronization Scheduler (EP-23.4).

A thin orchestration layer that periodically calls the existing
``ProviderSyncService`` (EP-23.3) for every organization that has opted
into automatic background sync — closing the loop EP-23.3's own "next
milestone recommendation" named explicitly: "a scheduler ... so usage data
flows without a user manually clicking 'Sync now'".

This module introduces **no** new collection, retry, provider, or
credential-decryption logic. Every one of those concerns already has an
owner:

    UsageSyncScheduler          — WHEN to sync (interval, concurrency, locking)
        │
        ▼
    ProviderSyncService         — WHICH connections, credential decrypt (EP-23.3)
        │
        ▼
    UsageCollectionService      — HOW to page/normalize/persist (EP-08)
        │
        ▼
    ProviderHttpClient +
    ExponentialRetryPolicy      — retry transient HTTP failures (EP-06/EP-07)

Why not extend ``app.usage.background.BackgroundCollectionFramework``
(EP-08)? That class is a manual-submit task tracker, not an interval-based
scheduler — it has no notion of "every N minutes", and its
``session_factory`` parameter expects an async *callable* returning an
already-open ``AsyncSession`` (``await session_factory()``), which is a
different shape than ``AppContainer.session_factory``'s
``async_sessionmaker`` (used via ``async with session_factory() as
session:`` everywhere else in this codebase, including ``app.api.deps.
get_db``). It also calls ``UsageCollectionService`` directly with an
env-var-keyed config, bypassing the customer-credential path
``ProviderSyncService`` exists specifically to provide. Wrapping it would
mean fixing a factory-signature mismatch and re-deriving the
credential-aware call path it was never given — at that point it is not
"the existing scheduler," it is a rewrite wearing the old class's name.
``BackgroundCollectionFramework`` is left exactly as EP-08/EP-23.3 already
documented it: dormant, unwired, untouched.

Concurrency
-----------
Two independent guards, layered so the scheduler is safe both as a single
process and as multiple horizontally-scaled API workers sharing one Redis:

1. **In-process**: ``_running_org_ids`` — a plain ``set[UUID]`` checked
   before dispatch. Free, catches the common case (one worker, one tick
   loop) with zero I/O.
2. **Cross-process**: a Redis ``SET key NX EX ttl`` lock
   (``scheduler:lock:org:{org_id}``), reusing the same Redis client already
   on ``AppContainer`` (no new infrastructure). If Redis is unreachable, the
   lock check degrades to "always allowed" — the same graceful-degradation
   precedent ``app.auth.rate_limit``'s ``_RedisBackend``/fallback already
   established for this codebase, so a Redis outage narrows the safety net
   to the in-process guard rather than blocking sync entirely.

A ``max_concurrent_orgs`` asyncio.Semaphore additionally caps how many org
syncs run at once *within this process*, so a large backlog of due
organizations queues rather than firing unboundedly.

Checkpointing
-------------
No new checkpoint logic. "Due" is computed fresh on every tick from the
persisted ``UsageCollectionRun`` table (``get_latest_for_org``,
``triggered_by=SCHEDULED``) — never from an in-memory "next run" timestamp.
This is what makes initial sync, incremental sync, resume-after-interruption,
and recovery-after-deployment-restart all "just work" with no special-casing:
every one of those is simply "what does the database say happened last,"
which survives a process restart by construction.
"""

from __future__ import annotations

import asyncio
import contextlib
import enum
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import structlog

from app.alerts.dispatcher import AlertService
from app.budgets.service import BudgetEvaluationService
from app.models.usage_collection_run import CollectionRunStatus, CollectionTrigger
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.usage_collection_run_repository import UsageCollectionRunRepository
from app.services.provider_sync_service import ProviderSyncService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.realtime.event_bus import EventBus

log = structlog.get_logger(__name__)

# ── Configurable intervals (spec: 5m / 15m / 1h / 6h / daily) ──────────────────
INTERVAL_PRESETS: dict[str, int] = {
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "6h": 21600,
    "24h": 86400,
}
DEFAULT_INTERVAL_SECONDS = INTERVAL_PRESETS["1h"]
MIN_INTERVAL_SECONDS = INTERVAL_PRESETS["5m"]
MAX_INTERVAL_SECONDS = INTERVAL_PRESETS["24h"]

# How often the scheduler's own loop wakes up to check which orgs are due.
# Independent of any org's configured sync interval — this is the tick
# granularity, not a sync interval itself.
DEFAULT_TICK_INTERVAL_SECONDS = 60

_LOCK_KEY_PREFIX = "scheduler:lock:org:"


def interval_seconds_for(sync_settings: dict[str, Any]) -> int:
    """Extract and clamp the configured interval from an org's sync_settings.

    Clamped defensively (not just validated on write) so a value written by
    a future client version, or edited directly in the database, can never
    make the scheduler busy-loop below 5 minutes or effectively never run.
    """
    raw = sync_settings.get("interval_seconds", DEFAULT_INTERVAL_SECONDS)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_INTERVAL_SECONDS
    return max(MIN_INTERVAL_SECONDS, min(MAX_INTERVAL_SECONDS, value))


def auto_sync_enabled_for(sync_settings: dict[str, Any]) -> bool:
    return bool(sync_settings.get("auto_sync_enabled", False))


def interval_label_for(interval_seconds: int) -> str:
    """Reverse lookup into INTERVAL_PRESETS for API responses.

    Falls back to the nearest preset rather than raising if a stored value
    doesn't land on an exact preset boundary (defensive, mirrors
    ``interval_seconds_for``'s own clamping).
    """
    for label, seconds in INTERVAL_PRESETS.items():
        if seconds == interval_seconds:
            return label
    nearest = min(INTERVAL_PRESETS.items(), key=lambda kv: abs(kv[1] - interval_seconds))
    return nearest[0]


class SchedulerJobStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class SchedulerJobRecord:
    """In-memory record of one scheduler-dispatched organization sync.

    Deliberately in-memory only (mirrors ``BackgroundCollectionFramework``'s
    ``CollectionTaskRecord`` precedent from EP-08) — the durable outcome of
    each connection synced is already persisted as a ``UsageCollectionRun``
    by ``ProviderSyncService``/``UsageCollectionService``; this record exists
    only to answer "what has the scheduler process itself been doing"
    for the monitoring endpoint, and resets on restart by design (the
    persisted runs are the source of truth for "did this org actually get
    synced," not this record).
    """

    job_id: uuid.UUID
    organization_id: uuid.UUID
    status: SchedulerJobStatus
    queued_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    connections_synced: int = 0
    connections_failed: int = 0
    records_imported: int = 0
    retry_count: int = 0
    error: str | None = None

    @property
    def duration_seconds(self) -> float | None:
        if self.started_at is None:
            return None
        end = self.completed_at or datetime.now(UTC)
        return (end - self.started_at).total_seconds()

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": str(self.job_id),
            "organization_id": str(self.organization_id),
            "status": self.status.value,
            "queued_at": self.queued_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "connections_synced": self.connections_synced,
            "connections_failed": self.connections_failed,
            "records_imported": self.records_imported,
            "retry_count": self.retry_count,
            "duration_seconds": self.duration_seconds,
            "error": self.error,
        }


@dataclass
class SchedulerOrgStatus:
    """Derived view of one organization's scheduler configuration + state."""

    organization_id: uuid.UUID
    auto_sync_enabled: bool
    interval_seconds: int
    last_sync_at: datetime | None
    last_sync_status: str | None
    next_sync_at: datetime | None
    current_job: SchedulerJobRecord | None


class UsageSyncScheduler:
    """Periodically syncs every organization with automatic sync enabled.

    ``session_factory`` must be an ``async_sessionmaker[AsyncSession]`` (the
    same object ``AppContainer.session_factory`` already is) — used as
    ``async with session_factory() as session:``, matching ``app.api.deps.
    get_db`` and every other non-request call site in this codebase.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        redis: Any | None = None,  # noqa: ANN401 — redis.asyncio.Redis | None
        event_bus: EventBus | None = None,
        tick_interval_seconds: int = DEFAULT_TICK_INTERVAL_SECONDS,
        max_concurrent_orgs: int = 5,
        job_history_limit: int = 200,
        sync_service_factory: Callable[[AsyncSession], ProviderSyncService] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._redis = redis
        # EP-24.2: reused to fire budget alerts right after a successful
        # sync (see _run_job below) — the same EventBus AlertService.fire()
        # already publishes through for every other alert type. None is a
        # valid, tested configuration (e.g. a container built without
        # real-time delivery wired up yet) — budget evaluation is simply
        # skipped for that job rather than failing the sync itself.
        self._event_bus = event_bus
        self._tick_interval_seconds = tick_interval_seconds
        self._semaphore = asyncio.Semaphore(max_concurrent_orgs)
        self._sync_service_factory = sync_service_factory or ProviderSyncService
        self._jobs: deque[SchedulerJobRecord] = deque(maxlen=job_history_limit)
        self._running_org_ids: set[uuid.UUID] = set()
        self._loop_task: asyncio.Task[None] | None = None
        self._started_at: datetime | None = None
        self._tick_count = 0
        self._lock = asyncio.Lock()  # guards _running_org_ids/_jobs mutation

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the periodic tick loop. No-op if already started."""
        if self._loop_task is not None:
            return
        self._started_at = datetime.now(UTC)
        self._loop_task = asyncio.create_task(self._run_loop(), name="usage-sync-scheduler")
        log.info(
            "scheduler_started",
            tick_interval_seconds=self._tick_interval_seconds,
        )

    async def stop(self) -> None:
        """Cancel the tick loop and wait for it to exit. Safe to call twice."""
        if self._loop_task is None:
            return
        self._loop_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._loop_task
        self._loop_task = None
        log.info("scheduler_stopped")

    @property
    def is_running(self) -> bool:
        return self._loop_task is not None and not self._loop_task.done()

    async def _run_loop(self) -> None:
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                # A failed tick (e.g. a transient DB blip while listing orgs)
                # must never kill the loop — the next tick tries again.
                log.exception("scheduler_tick_failed")
            await asyncio.sleep(self._tick_interval_seconds)

    # ── Tick ───────────────────────────────────────────────────────────────────

    async def tick(self) -> list[SchedulerJobRecord]:
        """One scheduling pass: discover due orgs, dispatch sync jobs.

        Returns the jobs dispatched this tick (empty if nothing was due) —
        primarily so tests can assert on a single deterministic tick rather
        than racing the background loop.
        """
        self._tick_count += 1
        dispatched: list[SchedulerJobRecord] = []
        cursor: str | None = None

        while True:
            async with self._session_factory() as session:
                org_repo = OrganizationRepository(session)
                page = await org_repo.list_auto_sync_enabled(cursor=cursor)
                org_snapshots = [(org.id, dict(org.sync_settings)) for org in page.items]

            for org_id, sync_settings in org_snapshots:
                job = await self._maybe_dispatch(org_id, sync_settings)
                if job is not None:
                    dispatched.append(job)

            if not page.next_cursor:
                break
            cursor = page.next_cursor

        return dispatched

    async def _maybe_dispatch(
        self, organization_id: uuid.UUID, sync_settings: dict[str, Any]
    ) -> SchedulerJobRecord | None:
        # Skip already-running jobs (in-process fast path — no I/O).
        if organization_id in self._running_org_ids:
            log.debug("scheduler_skip_already_running", organization_id=str(organization_id))
            return None

        interval_seconds = interval_seconds_for(sync_settings)
        due, _next_run = await self._is_due(organization_id, interval_seconds)
        if not due:
            return None

        # Skip already-running jobs (cross-process guard — Redis-backed).
        if not await self._acquire_lock(organization_id, interval_seconds):
            log.debug("scheduler_skip_locked_elsewhere", organization_id=str(organization_id))
            return None

        job = SchedulerJobRecord(
            job_id=uuid.uuid4(),
            organization_id=organization_id,
            status=SchedulerJobStatus.QUEUED,
            queued_at=datetime.now(UTC),
            retry_count=self._consecutive_failure_streak(organization_id),
        )
        async with self._lock:
            self._jobs.append(job)
            self._running_org_ids.add(organization_id)

        asyncio.create_task(  # noqa: RUF006 — fire-and-forget by design; awaited via job record
            self._run_job(job), name=f"usage-sync-org-{organization_id}"
        )
        return job

    async def _is_due(
        self, organization_id: uuid.UUID, interval_seconds: int
    ) -> tuple[bool, datetime]:
        """Never-synced orgs are always due; otherwise due once the interval
        has elapsed since the last SCHEDULED run's completion."""
        async with self._session_factory() as session:
            run_repo = UsageCollectionRunRepository(session)
            latest = await run_repo.get_latest_for_org(
                organization_id, triggered_by=CollectionTrigger.SCHEDULED
            )
        now = datetime.now(UTC)
        if latest is None:
            return True, now
        anchor = latest.completed_at or latest.started_at
        next_run = anchor + timedelta(seconds=interval_seconds)
        return now >= next_run, next_run

    def _consecutive_failure_streak(self, organization_id: uuid.UUID) -> int:
        """Count trailing FAILED scheduler jobs for this org in this
        process's job history — surfaced as ``retry_count`` so the frontend
        can show "this org's background sync has failed N times in a row,"
        distinct from the per-HTTP-request retries already handled inside
        ``ProviderHttpClient`` (EP-06/EP-07), which this scheduler does not
        re-implement or re-count."""
        streak = 0
        for record in reversed(self._jobs):
            if record.organization_id != organization_id:
                continue
            if record.status != SchedulerJobStatus.FAILED:
                break
            streak += 1
        return streak

    # ── Locking ────────────────────────────────────────────────────────────────

    def _lock_key(self, organization_id: uuid.UUID) -> str:
        return f"{_LOCK_KEY_PREFIX}{organization_id}"

    async def _acquire_lock(self, organization_id: uuid.UUID, interval_seconds: int) -> bool:
        if self._redis is None:
            return True
        ttl = max(60, min(interval_seconds, MAX_INTERVAL_SECONDS))
        try:
            acquired = await self._redis.set(self._lock_key(organization_id), "1", nx=True, ex=ttl)
        except Exception:
            # Redis unreachable: degrade to the in-process guard only,
            # matching app.auth.rate_limit's fail-open-to-in-memory precedent
            # rather than blocking sync entirely on a Redis outage.
            log.warning("scheduler_lock_redis_unavailable", organization_id=str(organization_id))
            return True
        return bool(acquired)

    async def _release_lock(self, organization_id: uuid.UUID) -> None:
        if self._redis is None:
            return
        with contextlib.suppress(Exception):
            await self._redis.delete(self._lock_key(organization_id))

    # ── Job execution ──────────────────────────────────────────────────────────

    async def _run_job(self, job: SchedulerJobRecord) -> None:
        organization_id = job.organization_id
        logger = log.bind(job_id=str(job.job_id), organization_id=str(organization_id))
        async with self._semaphore:
            job.status = SchedulerJobStatus.RUNNING
            job.started_at = datetime.now(UTC)
            logger.info("scheduler_job_started")
            try:
                async with self._session_factory() as session, session.begin():
                    sync_service = self._sync_service_factory(session)
                    runs = await sync_service.sync_all_connections(
                        organization_id=organization_id,
                        triggered_by=CollectionTrigger.SCHEDULED,
                    )
                    # EP-24.2: evaluate budgets in the same session/
                    # transaction as the sync that just ran, right after —
                    # "After each successful usage synchronization: Evaluate
                    # budgets -> Generate alerts -> Persist notifications ->
                    # Update dashboard." A sync with zero successful runs
                    # still gets evaluated (spend may be unchanged, but a
                    # newly-created budget or a threshold crossed by a prior
                    # sync should still surface on the very next tick).
                    event_bus = self._event_bus
                    if event_bus is not None:
                        await self._evaluate_budgets(session, organization_id, event_bus, logger)
                job.connections_synced = sum(
                    1 for r in runs if r.status == CollectionRunStatus.COMPLETED
                )
                job.connections_failed = sum(
                    1 for r in runs if r.status == CollectionRunStatus.FAILED
                )
                job.records_imported = sum(r.events_collected for r in runs)
                job.status = (
                    SchedulerJobStatus.COMPLETED
                    if job.connections_failed == 0
                    else SchedulerJobStatus.FAILED
                )
                logger.info(
                    "scheduler_job_completed",
                    connections_synced=job.connections_synced,
                    connections_failed=job.connections_failed,
                    records_imported=job.records_imported,
                )
            except Exception as exc:
                # Never log the raw exception body — provider adapters may
                # embed request context; only the type name is safe (same
                # convention ProviderSyncService.sync_connection uses).
                job.status = SchedulerJobStatus.FAILED
                job.error = f"Scheduler job failed: {type(exc).__name__}"
                logger.warning("scheduler_job_failed", error_type=type(exc).__name__)
            finally:
                job.completed_at = datetime.now(UTC)
                async with self._lock:
                    self._running_org_ids.discard(organization_id)
                await self._release_lock(organization_id)

    async def _evaluate_budgets(
        self,
        session: AsyncSession,
        organization_id: uuid.UUID,
        event_bus: EventBus,
        logger: structlog.typing.FilteringBoundLogger,
    ) -> None:
        """EP-24.2 post-sync hook. Reuses `BudgetEvaluationService` (which
        itself reuses `UsageCostRecordRepository`'s existing aggregate
        queries and `AlertService.fire()`'s existing dedup/publish
        machinery) — this method adds no aggregation or alerting logic of
        its own, only the "call it after a sync" wiring. A failure here
        never fails the sync job itself — a budget misconfiguration must
        not turn into a false "sync failed" for a completely unrelated
        provider connection."""
        try:
            alert_service = AlertService(session, event_bus)
            evaluator = BudgetEvaluationService(session, alert_service=alert_service)
            await evaluator.evaluate_and_alert(organization_id)
        except Exception:
            logger.warning("scheduler_budget_evaluation_failed", exc_info=True)

    # ── Status / monitoring ────────────────────────────────────────────────────

    def current_job_for(self, organization_id: uuid.UUID) -> SchedulerJobRecord | None:
        for record in reversed(self._jobs):
            if record.organization_id == organization_id:
                return record
        return None

    def jobs_for(self, organization_id: uuid.UUID, *, limit: int = 20) -> list[SchedulerJobRecord]:
        matches = [r for r in reversed(self._jobs) if r.organization_id == organization_id]
        return matches[:limit]

    async def get_org_status(
        self, organization_id: uuid.UUID, sync_settings: dict[str, Any]
    ) -> SchedulerOrgStatus:
        """Read-only, no side effects — safe to call from a GET endpoint."""
        enabled = auto_sync_enabled_for(sync_settings)
        interval_seconds = interval_seconds_for(sync_settings)

        async with self._session_factory() as session:
            run_repo = UsageCollectionRunRepository(session)
            latest = await run_repo.get_latest_for_org(
                organization_id, triggered_by=CollectionTrigger.SCHEDULED
            )

        last_sync_at = (latest.completed_at if latest else None) if latest else None
        last_sync_status = latest.status.value if latest else None
        next_sync_at: datetime | None = None
        if enabled:
            if latest is None:
                next_sync_at = datetime.now(UTC)
            else:
                anchor = latest.completed_at or latest.started_at
                next_sync_at = anchor + timedelta(seconds=interval_seconds)

        return SchedulerOrgStatus(
            organization_id=organization_id,
            auto_sync_enabled=enabled,
            interval_seconds=interval_seconds,
            last_sync_at=last_sync_at,
            last_sync_status=last_sync_status,
            next_sync_at=next_sync_at,
            current_job=self.current_job_for(organization_id),
        )

    def monitoring_snapshot(self) -> dict[str, Any]:
        """Global (all-organizations) job counters for the monitoring view.

        Computed from this process's in-memory job history — see
        ``SchedulerJobRecord``'s docstring for why that is the right scope
        for "is the scheduler itself healthy" rather than a durable,
        cross-restart metric.
        """
        jobs = list(self._jobs)
        completed = [j for j in jobs if j.status == SchedulerJobStatus.COMPLETED]
        failed = [j for j in jobs if j.status == SchedulerJobStatus.FAILED]
        running = [j for j in jobs if j.status == SchedulerJobStatus.RUNNING]
        queued = [j for j in jobs if j.status == SchedulerJobStatus.QUEUED]
        durations = [j.duration_seconds for j in jobs if j.duration_seconds is not None]
        last_execution = max((j.completed_at for j in jobs if j.completed_at), default=None)

        return {
            "is_running": self.is_running,
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "tick_count": self._tick_count,
            "tick_interval_seconds": self._tick_interval_seconds,
            "active_jobs": len(running),
            "queued_jobs": len(queued),
            "completed_jobs": len(completed),
            "failed_jobs": len(failed),
            "average_duration_seconds": (
                round(sum(durations) / len(durations), 3) if durations else None
            ),
            "last_execution": last_execution.isoformat() if last_execution else None,
        }
