"""Background collection framework — F-047 (EP-08).

Provides a lightweight framework for executing usage collection runs as
background asyncio tasks.  Scheduling is deliberately NOT implemented here;
EP-09/EP-10 will add the scheduler.

Features
--------
- Manual execution via ``BackgroundCollectionFramework.submit()``
- Per-task cancellation via ``cancel(task_id)``
- Status and progress tracking (in-memory; resets on restart)
- Structured execution logs via structlog
- No scheduled jobs — callers trigger explicitly

Usage
-----
::

    framework = BackgroundCollectionFramework(session_factory)
    task_id = await framework.submit(
        organization_id=org_id,
        provider="openai",
        start_date=start,
        end_date=end,
    )
    status = framework.get_status(task_id)
    await framework.cancel(task_id)
"""

from __future__ import annotations

import asyncio
import enum
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog

log = structlog.get_logger(__name__)


class TaskStatus(enum.StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CollectionTaskRecord:
    """In-memory state for a single background collection task."""

    __slots__ = (
        "task_id",
        "organization_id",
        "provider",
        "start_date",
        "end_date",
        "status",
        "run_id",
        "error",
        "submitted_at",
        "started_at",
        "completed_at",
        "_asyncio_task",
    )

    def __init__(
        self,
        *,
        task_id: uuid.UUID,
        organization_id: uuid.UUID,
        provider: str,
        start_date: datetime,
        end_date: datetime,
    ) -> None:
        self.task_id = task_id
        self.organization_id = organization_id
        self.provider = provider
        self.start_date = start_date
        self.end_date = end_date
        self.status = TaskStatus.PENDING
        self.run_id: uuid.UUID | None = None
        self.error: str | None = None
        self.submitted_at: datetime = datetime.now(UTC)
        self.started_at: datetime | None = None
        self.completed_at: datetime | None = None
        self._asyncio_task: asyncio.Task[Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": str(self.task_id),
            "organization_id": str(self.organization_id),
            "provider": self.provider,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "status": self.status,
            "run_id": str(self.run_id) if self.run_id else None,
            "error": self.error,
            "submitted_at": self.submitted_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class BackgroundCollectionFramework:
    """Framework for managing background usage collection tasks.

    ``session_factory`` must be an async callable that returns an
    ``AsyncSession`` when called.  The framework creates one session
    per task so tasks don't share transaction state.

    Parameters
    ----------
    session_factory:
        Async callable ``() -> AsyncSession``.
    registry:
        Optional ``ProviderRegistry`` override (for testing).
    max_concurrent:
        Maximum number of simultaneously running tasks.
    """

    def __init__(
        self,
        session_factory: Any,
        *,
        registry: Any | None = None,
        max_concurrent: int = 5,
    ) -> None:
        self._session_factory = session_factory
        self._registry = registry
        self._max_concurrent = max_concurrent
        self._tasks: dict[uuid.UUID, CollectionTaskRecord] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def submit(
        self,
        *,
        organization_id: uuid.UUID,
        provider: str,
        start_date: datetime,
        end_date: datetime,
        provider_connection_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        """Schedule a collection task and return its task_id.

        The task runs concurrently in the background.  Poll ``get_status()``
        to track progress.
        """
        task_id = uuid.uuid4()
        record = CollectionTaskRecord(
            task_id=task_id,
            organization_id=organization_id,
            provider=provider,
            start_date=start_date,
            end_date=end_date,
        )
        self._tasks[task_id] = record

        asyncio_task = asyncio.create_task(
            self._run_task(
                record=record,
                provider_connection_id=provider_connection_id,
                project_id=project_id,
            ),
            name=f"usage-collect-{task_id}",
        )
        record._asyncio_task = asyncio_task

        log.info(
            "background_task_submitted",
            task_id=str(task_id),
            provider=provider,
            organization_id=str(organization_id),
        )
        return task_id

    async def cancel(self, task_id: uuid.UUID) -> bool:
        """Cancel a pending or running task.

        Returns ``True`` if the task was found and cancelled, ``False`` if it
        had already completed or was not found.
        """
        record = self._tasks.get(task_id)
        if record is None:
            return False
        if record._asyncio_task and not record._asyncio_task.done():
            record._asyncio_task.cancel()
            record.status = TaskStatus.CANCELLED
            record.completed_at = datetime.now(UTC)
            log.info("background_task_cancelled", task_id=str(task_id))
            return True
        return False

    def get_status(self, task_id: uuid.UUID) -> dict[str, Any] | None:
        """Return the current status dict for a task, or None if not found."""
        record = self._tasks.get(task_id)
        return record.to_dict() if record else None

    def list_tasks(
        self,
        *,
        organization_id: uuid.UUID | None = None,
        provider: str | None = None,
        status: TaskStatus | None = None,
    ) -> list[dict[str, Any]]:
        """Return status dicts for all matching tasks (most recent first)."""
        results = list(self._tasks.values())
        if organization_id:
            results = [r for r in results if r.organization_id == organization_id]
        if provider:
            results = [r for r in results if r.provider == provider]
        if status:
            results = [r for r in results if r.status == status]
        results.sort(key=lambda r: r.submitted_at, reverse=True)
        return [r.to_dict() for r in results]

    def running_count(self) -> int:
        return sum(
            1 for r in self._tasks.values() if r.status == TaskStatus.RUNNING
        )

    # ── Private ────────────────────────────────────────────────────────────────

    async def _run_task(
        self,
        *,
        record: CollectionTaskRecord,
        provider_connection_id: uuid.UUID | None,
        project_id: uuid.UUID | None,
    ) -> None:
        from app.models.usage_collection_run import CollectionTrigger
        from app.usage.service import UsageCollectionService

        async with self._semaphore:
            record.status = TaskStatus.RUNNING
            record.started_at = datetime.now(UTC)
            log.info("background_task_started", task_id=str(record.task_id))

            try:
                session = await self._session_factory()
                async with session.begin():
                    service = UsageCollectionService(
                        session,
                        registry=self._registry,
                    )
                    run = await service.collect(
                        organization_id=record.organization_id,
                        provider=record.provider,
                        start_date=record.start_date,
                        end_date=record.end_date,
                        provider_connection_id=provider_connection_id,
                        project_id=project_id,
                        triggered_by=CollectionTrigger.SCHEDULED,
                    )
                    record.run_id = run.id

                record.status = TaskStatus.COMPLETED
                record.completed_at = datetime.now(UTC)
                log.info(
                    "background_task_completed",
                    task_id=str(record.task_id),
                    run_id=str(run.id),
                )

            except asyncio.CancelledError:
                record.status = TaskStatus.CANCELLED
                record.completed_at = datetime.now(UTC)
                log.info("background_task_cancelled_mid_run", task_id=str(record.task_id))
                raise

            except Exception as exc:
                record.status = TaskStatus.FAILED
                record.error = str(exc)
                record.completed_at = datetime.now(UTC)
                log.warning(
                    "background_task_failed",
                    task_id=str(record.task_id),
                    error=str(exc),
                )
