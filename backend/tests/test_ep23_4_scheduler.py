"""Tests for the Background Usage Synchronization Scheduler (EP-23.4).

Covers:
  - ``UsageSyncScheduler.tick()`` / ``_maybe_dispatch`` — due-detection,
    skip-already-running (in-process + Redis), initial vs. incremental sync
  - Concurrency — in-process guard, Redis lock acquire/release, semaphore
  - Job execution — success/failure derived from ``ProviderSyncService.
    sync_all_connections`` (reused, never reimplemented), never retries
    auth failures itself (delegates to the existing HTTP retry policy)
  - ``get_org_status`` / ``monitoring_snapshot`` — read-only derivation
  - API: GET scheduler/status, PATCH scheduler/settings, GET scheduler/jobs
    — response shape and RBAC (PROVIDER_READ / PROVIDER_WRITE)

All tests are hermetic — no network calls, no real database, no real Redis,
no real asyncio sleep loop (tests call ``tick()`` directly rather than
starting the background loop).
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.models.membership import Membership, MembershipRole
from app.models.organization import Organization, OrganizationStatus
from app.models.usage_collection_run import CollectionRunStatus, CollectionTrigger
from app.models.user import User
from app.repositories.base_repository import CursorPage
from app.services.usage_sync_scheduler import (
    DEFAULT_INTERVAL_SECONDS,
    INTERVAL_PRESETS,
    SchedulerJobStatus,
    UsageSyncScheduler,
    auto_sync_enabled_for,
    interval_label_for,
    interval_seconds_for,
)
from tests.conftest import make_org

_ORG_ID = uuid.uuid4()
_NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


def _page(items: list[Any], next_cursor: str | None = None) -> CursorPage[Any]:
    return CursorPage(items=items, next_cursor=next_cursor, has_more=next_cursor is not None)


def _session_factory_for(session: Any) -> Any:
    """Return an object usable as ``async with session_factory() as s:``."""

    @asynccontextmanager
    async def _ctx() -> Any:
        yield session

    factory = MagicMock()
    factory.side_effect = lambda: _ctx()
    return factory


def _make_run(
    *,
    status: CollectionRunStatus = CollectionRunStatus.COMPLETED,
    events_collected: int = 5,
) -> Any:
    from app.db.mixins import uuid7
    from app.models.usage_collection_run import UsageCollectionRun

    run = UsageCollectionRun()
    run.id = uuid7()
    run.organization_id = _ORG_ID
    run.provider = "openai"
    run.status = status
    run.triggered_by = CollectionTrigger.SCHEDULED
    run.started_at = _NOW
    run.completed_at = _NOW
    run.collection_start = _NOW - timedelta(days=1)
    run.collection_end = _NOW
    run.events_collected = events_collected
    run.events_failed = 0
    run.pages_fetched = 1
    run.collection_config = {}
    return run


# ══════════════════════════════════════════════════════════════════════════════
# Pure helper functions
# ══════════════════════════════════════════════════════════════════════════════


class TestIntervalHelpers:
    def test_default_interval_used_when_missing(self) -> None:
        assert interval_seconds_for({}) == DEFAULT_INTERVAL_SECONDS

    def test_valid_preset_passthrough(self) -> None:
        assert interval_seconds_for({"interval_seconds": 900}) == 900

    def test_clamped_below_minimum(self) -> None:
        assert interval_seconds_for({"interval_seconds": 1}) == INTERVAL_PRESETS["5m"]

    def test_clamped_above_maximum(self) -> None:
        assert interval_seconds_for({"interval_seconds": 999999}) == INTERVAL_PRESETS["24h"]

    def test_invalid_type_falls_back_to_default(self) -> None:
        assert interval_seconds_for({"interval_seconds": "not-a-number"}) == (
            DEFAULT_INTERVAL_SECONDS
        )

    def test_auto_sync_enabled_defaults_false(self) -> None:
        assert auto_sync_enabled_for({}) is False

    def test_auto_sync_enabled_true(self) -> None:
        assert auto_sync_enabled_for({"auto_sync_enabled": True}) is True

    def test_interval_label_round_trip(self) -> None:
        for label, seconds in INTERVAL_PRESETS.items():
            assert interval_label_for(seconds) == label

    def test_interval_label_nearest_fallback(self) -> None:
        # Between 15m (900) and 1h (3600) — closer to 900.
        assert interval_label_for(1000) == "15m"


# ══════════════════════════════════════════════════════════════════════════════
# tick() / dispatch / concurrency
# ══════════════════════════════════════════════════════════════════════════════


class TestTickDispatch:
    @pytest.mark.asyncio
    async def test_tick_dispatches_due_org_and_calls_sync_all_connections(self) -> None:
        org = make_org(sync_settings={"auto_sync_enabled": True, "interval_seconds": 3600})
        org.id = _ORG_ID

        org_repo = AsyncMock()
        org_repo.list_auto_sync_enabled.return_value = _page([org])

        run_repo = AsyncMock()
        run_repo.get_latest_for_org.return_value = None  # never synced -> due

        mock_sync_service = AsyncMock()
        mock_sync_service.sync_all_connections.return_value = [_make_run()]

        session_factory = _session_factory_for(MagicMock())

        with (
            patch(
                "app.services.usage_sync_scheduler.OrganizationRepository",
                return_value=org_repo,
            ),
            patch(
                "app.services.usage_sync_scheduler.UsageCollectionRunRepository",
                return_value=run_repo,
            ),
        ):
            scheduler = UsageSyncScheduler(
                session_factory,
                sync_service_factory=lambda _session: mock_sync_service,
            )
            dispatched = await scheduler.tick()
            assert len(dispatched) == 1
            job = dispatched[0]
            # Wait for the fire-and-forget task to finish.
            for _ in range(50):
                if job.status in (SchedulerJobStatus.COMPLETED, SchedulerJobStatus.FAILED):
                    break
                import asyncio

                await asyncio.sleep(0.01)

        assert job.status == SchedulerJobStatus.COMPLETED
        assert job.connections_synced == 1
        assert job.records_imported == 5
        mock_sync_service.sync_all_connections.assert_awaited_once()
        call_kwargs = mock_sync_service.sync_all_connections.call_args.kwargs
        assert call_kwargs["organization_id"] == _ORG_ID
        assert call_kwargs["triggered_by"] == CollectionTrigger.SCHEDULED

    @pytest.mark.asyncio
    async def test_tick_skips_org_not_yet_due(self) -> None:
        org = make_org(sync_settings={"auto_sync_enabled": True, "interval_seconds": 3600})
        org.id = _ORG_ID

        org_repo = AsyncMock()
        org_repo.list_auto_sync_enabled.return_value = _page([org])

        run_repo = AsyncMock()
        recent_run = _make_run(status=CollectionRunStatus.COMPLETED)
        recent_run.completed_at = datetime.now(UTC)  # just synced, not due for another hour
        run_repo.get_latest_for_org.return_value = recent_run

        session_factory = _session_factory_for(MagicMock())
        mock_sync_service = AsyncMock()

        with (
            patch(
                "app.services.usage_sync_scheduler.OrganizationRepository",
                return_value=org_repo,
            ),
            patch(
                "app.services.usage_sync_scheduler.UsageCollectionRunRepository",
                return_value=run_repo,
            ),
        ):
            scheduler = UsageSyncScheduler(
                session_factory, sync_service_factory=lambda _s: mock_sync_service
            )
            dispatched = await scheduler.tick()

        assert dispatched == []
        mock_sync_service.sync_all_connections.assert_not_called()

    @pytest.mark.asyncio
    async def test_tick_skips_org_with_auto_sync_disabled(self) -> None:
        """list_auto_sync_enabled() itself filters these out — confirms the
        repository query, not just the scheduler, does the excluding."""
        org_repo = AsyncMock()
        org_repo.list_auto_sync_enabled.return_value = _page([])

        session_factory = _session_factory_for(MagicMock())
        with patch(
            "app.services.usage_sync_scheduler.OrganizationRepository", return_value=org_repo
        ):
            scheduler = UsageSyncScheduler(session_factory)
            dispatched = await scheduler.tick()

        assert dispatched == []

    @pytest.mark.asyncio
    async def test_maybe_dispatch_skips_already_running_in_process(self) -> None:
        session_factory = _session_factory_for(MagicMock())
        scheduler = UsageSyncScheduler(session_factory)
        scheduler._running_org_ids.add(_ORG_ID)

        job = await scheduler._maybe_dispatch(_ORG_ID, {"auto_sync_enabled": True})
        assert job is None

    @pytest.mark.asyncio
    async def test_maybe_dispatch_skips_when_redis_lock_held_elsewhere(self) -> None:
        run_repo = AsyncMock()
        run_repo.get_latest_for_org.return_value = None  # due

        mock_redis = AsyncMock()
        mock_redis.set.return_value = False  # NX failed — another worker holds it

        session_factory = _session_factory_for(MagicMock())
        with patch(
            "app.services.usage_sync_scheduler.UsageCollectionRunRepository",
            return_value=run_repo,
        ):
            scheduler = UsageSyncScheduler(session_factory, redis=mock_redis)
            job = await scheduler._maybe_dispatch(
                _ORG_ID, {"auto_sync_enabled": True, "interval_seconds": 3600}
            )

        assert job is None
        mock_redis.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_redis_unavailable_degrades_to_allowed(self) -> None:
        """A Redis error must never block sync entirely — falls back to the
        in-process guard only, matching app.auth.rate_limit's precedent."""
        mock_redis = AsyncMock()
        mock_redis.set.side_effect = ConnectionError("redis down")

        session_factory = _session_factory_for(MagicMock())
        scheduler = UsageSyncScheduler(session_factory, redis=mock_redis)
        acquired = await scheduler._acquire_lock(_ORG_ID, 3600)
        assert acquired is True

    @pytest.mark.asyncio
    async def test_no_redis_configured_always_acquires(self) -> None:
        session_factory = _session_factory_for(MagicMock())
        scheduler = UsageSyncScheduler(session_factory, redis=None)
        assert await scheduler._acquire_lock(_ORG_ID, 3600) is True


# ══════════════════════════════════════════════════════════════════════════════
# Job execution — success / failure / retry_count
# ══════════════════════════════════════════════════════════════════════════════


class TestJobExecution:
    @pytest.mark.asyncio
    async def test_run_job_failure_marks_job_failed_and_releases_lock(self) -> None:
        mock_sync_service = AsyncMock()
        mock_sync_service.sync_all_connections.side_effect = RuntimeError("boom")
        mock_redis = AsyncMock()
        mock_redis.set.return_value = True

        session_factory = _session_factory_for(MagicMock())
        scheduler = UsageSyncScheduler(
            session_factory, redis=mock_redis, sync_service_factory=lambda _s: mock_sync_service
        )

        from app.services.usage_sync_scheduler import SchedulerJobRecord

        job = SchedulerJobRecord(
            job_id=uuid.uuid4(),
            organization_id=_ORG_ID,
            status=SchedulerJobStatus.QUEUED,
            queued_at=datetime.now(UTC),
        )
        scheduler._running_org_ids.add(_ORG_ID)
        await scheduler._run_job(job)

        assert job.status == SchedulerJobStatus.FAILED
        assert job.error is not None
        assert "RuntimeError" in job.error
        assert _ORG_ID not in scheduler._running_org_ids
        mock_redis.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_job_partial_failure_marks_job_failed(self) -> None:
        """One connection failing within the org marks the whole scheduler
        job FAILED even though sync_all_connections itself didn't raise —
        matches ProviderSyncService's per-connection FAILED-run contract."""
        mock_sync_service = AsyncMock()
        mock_sync_service.sync_all_connections.return_value = [
            _make_run(status=CollectionRunStatus.COMPLETED, events_collected=3),
            _make_run(status=CollectionRunStatus.FAILED, events_collected=0),
        ]

        session_factory = _session_factory_for(MagicMock())
        scheduler = UsageSyncScheduler(
            session_factory, sync_service_factory=lambda _s: mock_sync_service
        )

        from app.services.usage_sync_scheduler import SchedulerJobRecord

        job = SchedulerJobRecord(
            job_id=uuid.uuid4(),
            organization_id=_ORG_ID,
            status=SchedulerJobStatus.QUEUED,
            queued_at=datetime.now(UTC),
        )
        await scheduler._run_job(job)

        assert job.status == SchedulerJobStatus.FAILED
        assert job.connections_synced == 1
        assert job.connections_failed == 1
        assert job.records_imported == 3

    def test_retry_count_reflects_consecutive_failure_streak(self) -> None:
        session_factory = _session_factory_for(MagicMock())
        scheduler = UsageSyncScheduler(session_factory)

        from app.services.usage_sync_scheduler import SchedulerJobRecord

        other_org = uuid.uuid4()
        # Two prior failures for _ORG_ID, one success for a different org in
        # between (must not break the streak calculation for _ORG_ID).
        scheduler._jobs.append(
            SchedulerJobRecord(
                job_id=uuid.uuid4(),
                organization_id=_ORG_ID,
                status=SchedulerJobStatus.FAILED,
                queued_at=datetime.now(UTC),
            )
        )
        scheduler._jobs.append(
            SchedulerJobRecord(
                job_id=uuid.uuid4(),
                organization_id=other_org,
                status=SchedulerJobStatus.COMPLETED,
                queued_at=datetime.now(UTC),
            )
        )
        scheduler._jobs.append(
            SchedulerJobRecord(
                job_id=uuid.uuid4(),
                organization_id=_ORG_ID,
                status=SchedulerJobStatus.FAILED,
                queued_at=datetime.now(UTC),
            )
        )
        assert scheduler._consecutive_failure_streak(_ORG_ID) == 2

    def test_retry_count_resets_after_a_success(self) -> None:
        session_factory = _session_factory_for(MagicMock())
        scheduler = UsageSyncScheduler(session_factory)

        from app.services.usage_sync_scheduler import SchedulerJobRecord

        scheduler._jobs.append(
            SchedulerJobRecord(
                job_id=uuid.uuid4(),
                organization_id=_ORG_ID,
                status=SchedulerJobStatus.FAILED,
                queued_at=datetime.now(UTC),
            )
        )
        scheduler._jobs.append(
            SchedulerJobRecord(
                job_id=uuid.uuid4(),
                organization_id=_ORG_ID,
                status=SchedulerJobStatus.COMPLETED,
                queued_at=datetime.now(UTC),
            )
        )
        assert scheduler._consecutive_failure_streak(_ORG_ID) == 0


# ══════════════════════════════════════════════════════════════════════════════
# Checkpoint / due-detection (initial, incremental, restart-recovery)
# ══════════════════════════════════════════════════════════════════════════════


class TestDueDetection:
    @pytest.mark.asyncio
    async def test_never_synced_is_always_due(self) -> None:
        run_repo = AsyncMock()
        run_repo.get_latest_for_org.return_value = None
        session_factory = _session_factory_for(MagicMock())
        with patch(
            "app.services.usage_sync_scheduler.UsageCollectionRunRepository",
            return_value=run_repo,
        ):
            scheduler = UsageSyncScheduler(session_factory)
            due, _next = await scheduler._is_due(_ORG_ID, 3600)
        assert due is True

    @pytest.mark.asyncio
    async def test_recent_run_is_not_due(self) -> None:
        run_repo = AsyncMock()
        recent = _make_run()
        recent.completed_at = datetime.now(UTC)
        run_repo.get_latest_for_org.return_value = recent
        session_factory = _session_factory_for(MagicMock())
        with patch(
            "app.services.usage_sync_scheduler.UsageCollectionRunRepository",
            return_value=run_repo,
        ):
            scheduler = UsageSyncScheduler(session_factory)
            due, next_run = await scheduler._is_due(_ORG_ID, 3600)
        assert due is False
        assert next_run > datetime.now(UTC)

    @pytest.mark.asyncio
    async def test_stale_run_beyond_interval_is_due(self) -> None:
        """Simulates recovery after a deployment restart: the scheduler has
        no in-memory state, but the persisted run from before the restart
        is old enough that the org is due again on the very first tick."""
        run_repo = AsyncMock()
        stale = _make_run()
        stale.completed_at = datetime.now(UTC) - timedelta(hours=2)
        run_repo.get_latest_for_org.return_value = stale
        session_factory = _session_factory_for(MagicMock())
        with patch(
            "app.services.usage_sync_scheduler.UsageCollectionRunRepository",
            return_value=run_repo,
        ):
            scheduler = UsageSyncScheduler(session_factory)
            due, _next = await scheduler._is_due(_ORG_ID, 3600)
        assert due is True


# ══════════════════════════════════════════════════════════════════════════════
# get_org_status / monitoring_snapshot
# ══════════════════════════════════════════════════════════════════════════════


class TestStatusAndMonitoring:
    @pytest.mark.asyncio
    async def test_get_org_status_never_synced(self) -> None:
        run_repo = AsyncMock()
        run_repo.get_latest_for_org.return_value = None
        session_factory = _session_factory_for(MagicMock())
        with patch(
            "app.services.usage_sync_scheduler.UsageCollectionRunRepository",
            return_value=run_repo,
        ):
            scheduler = UsageSyncScheduler(session_factory)
            status = await scheduler.get_org_status(
                _ORG_ID, {"auto_sync_enabled": True, "interval_seconds": 3600}
            )
        assert status.auto_sync_enabled is True
        assert status.last_sync_at is None
        assert status.next_sync_at is not None  # due immediately

    @pytest.mark.asyncio
    async def test_get_org_status_disabled_has_no_next_sync(self) -> None:
        run_repo = AsyncMock()
        run_repo.get_latest_for_org.return_value = None
        session_factory = _session_factory_for(MagicMock())
        with patch(
            "app.services.usage_sync_scheduler.UsageCollectionRunRepository",
            return_value=run_repo,
        ):
            scheduler = UsageSyncScheduler(session_factory)
            status = await scheduler.get_org_status(_ORG_ID, {"auto_sync_enabled": False})
        assert status.next_sync_at is None

    def test_monitoring_snapshot_counts_by_status(self) -> None:
        session_factory = _session_factory_for(MagicMock())
        scheduler = UsageSyncScheduler(session_factory)

        from app.services.usage_sync_scheduler import SchedulerJobRecord

        completed = SchedulerJobRecord(
            job_id=uuid.uuid4(),
            organization_id=_ORG_ID,
            status=SchedulerJobStatus.COMPLETED,
            queued_at=datetime.now(UTC),
            started_at=datetime.now(UTC) - timedelta(seconds=10),
            completed_at=datetime.now(UTC),
        )
        failed = SchedulerJobRecord(
            job_id=uuid.uuid4(),
            organization_id=_ORG_ID,
            status=SchedulerJobStatus.FAILED,
            queued_at=datetime.now(UTC),
            started_at=datetime.now(UTC) - timedelta(seconds=4),
            completed_at=datetime.now(UTC),
        )
        scheduler._jobs.append(completed)
        scheduler._jobs.append(failed)

        snapshot = scheduler.monitoring_snapshot()
        assert snapshot["completed_jobs"] == 1
        assert snapshot["failed_jobs"] == 1
        assert snapshot["active_jobs"] == 0
        assert snapshot["queued_jobs"] == 0
        assert snapshot["average_duration_seconds"] is not None


# ══════════════════════════════════════════════════════════════════════════════
# Lifecycle — start/stop
# ══════════════════════════════════════════════════════════════════════════════


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_start_then_stop_is_clean(self) -> None:
        org_repo = AsyncMock()
        org_repo.list_auto_sync_enabled.return_value = _page([])
        session_factory = _session_factory_for(MagicMock())
        with patch(
            "app.services.usage_sync_scheduler.OrganizationRepository", return_value=org_repo
        ):
            scheduler = UsageSyncScheduler(session_factory, tick_interval_seconds=3600)
            assert scheduler.is_running is False
            await scheduler.start()
            assert scheduler.is_running is True
            await scheduler.start()  # no-op, must not raise or double-start
            await scheduler.stop()
            assert scheduler.is_running is False
            await scheduler.stop()  # no-op, must not raise


# ══════════════════════════════════════════════════════════════════════════════
# API: GET/PATCH scheduler/status, scheduler/settings, scheduler/jobs
# ══════════════════════════════════════════════════════════════════════════════


def _override_auth(app: Any, *, caller_role: MembershipRole) -> tuple[Any, Any]:
    from app.api.deps import get_db
    from app.auth.dependencies import get_current_user

    mock_user = MagicMock(spec=User)
    mock_user.email = "caller@example.com"
    mock_user.status = "active"

    async def mock_get_user() -> User:
        return mock_user

    async def mock_get_db() -> Any:
        yield AsyncMock()

    app.dependency_overrides[get_current_user] = mock_get_user
    app.dependency_overrides[get_db] = mock_get_db

    org = MagicMock(spec=Organization)
    org.id = _ORG_ID
    org.status = OrganizationStatus.ACTIVE

    caller_membership = MagicMock(spec=Membership)
    caller_membership.role = caller_role

    org_repo = MagicMock()
    org_repo.get = AsyncMock(return_value=org)
    mem_repo_for_org_lookup = MagicMock()
    mem_repo_for_org_lookup.get_by_org_and_email = AsyncMock(return_value=caller_membership)

    return org_repo, mem_repo_for_org_lookup


class TestSchedulerStatusEndpoint:
    @pytest.mark.asyncio
    async def test_unauthenticated_is_401(self, app: Any) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get(
                f"/v1/organizations/{_ORG_ID}/provider-connections/scheduler/status"
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_viewer_can_read_status(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.VIEWER)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                target_org = make_org(sync_settings={"auto_sync_enabled": True})
                target_org.id = _ORG_ID
                with (
                    patch(
                        "app.api.v1.provider_connections.OrganizationRepository.get",
                        new=AsyncMock(return_value=target_org),
                    ),
                    patch(
                        "app.services.usage_sync_scheduler.UsageCollectionRunRepository"
                        ".get_latest_for_org",
                        new=AsyncMock(return_value=None),
                    ),
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.get(
                            f"/v1/organizations/{_ORG_ID}/provider-connections/scheduler/status"
                        )
            assert resp.status_code == 200
            body = resp.json()
            assert body["auto_sync_enabled"] is True
            assert body["interval"] == "1h"
            assert "monitoring" in body
            assert body["scheduler_health"] in {"healthy", "not_running", "degraded"}
        finally:
            app.dependency_overrides.clear()


class TestSchedulerSettingsEndpoint:
    @pytest.mark.asyncio
    async def test_admin_can_update_settings(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.ADMIN)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                target_org = make_org(sync_settings={})
                target_org.id = _ORG_ID
                updated_org = make_org(
                    sync_settings={"auto_sync_enabled": True, "interval_seconds": 900}
                )
                updated_org.id = _ORG_ID

                with (
                    patch(
                        "app.api.v1.provider_connections.OrganizationRepository.get",
                        new=AsyncMock(return_value=target_org),
                    ),
                    patch(
                        "app.api.v1.provider_connections.OrganizationRepository.update",
                        new=AsyncMock(return_value=updated_org),
                    ) as update_mock,
                    patch(
                        "app.services.usage_sync_scheduler.UsageCollectionRunRepository"
                        ".get_latest_for_org",
                        new=AsyncMock(return_value=None),
                    ),
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.patch(
                            f"/v1/organizations/{_ORG_ID}/provider-connections/scheduler/settings",
                            json={"auto_sync_enabled": True, "interval": "15m"},
                        )
            assert resp.status_code == 200
            body = resp.json()
            assert body["auto_sync_enabled"] is True
            assert body["interval"] == "15m"
            update_mock.assert_awaited_once()
            call_kwargs = update_mock.call_args.kwargs
            assert call_kwargs["sync_settings"] == {
                "auto_sync_enabled": True,
                "interval_seconds": 900,
            }
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_viewer_cannot_update_settings(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.VIEWER)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.patch(
                        f"/v1/organizations/{_ORG_ID}/provider-connections/scheduler/settings",
                        json={"auto_sync_enabled": True},
                    )
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_member_cannot_update_settings(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.MEMBER)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.patch(
                        f"/v1/organizations/{_ORG_ID}/provider-connections/scheduler/settings",
                        json={"auto_sync_enabled": True},
                    )
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()


class TestSchedulerJobsEndpoint:
    @pytest.mark.asyncio
    async def test_viewer_can_list_jobs(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.VIEWER)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                target_org = make_org(sync_settings={})
                target_org.id = _ORG_ID
                with patch(
                    "app.api.v1.provider_connections.OrganizationRepository.get",
                    new=AsyncMock(return_value=target_org),
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.get(
                            f"/v1/organizations/{_ORG_ID}/provider-connections/scheduler/jobs"
                        )
            assert resp.status_code == 200
            body = resp.json()
            assert body["jobs"] == []
            assert body["total"] == 0
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_unknown_org_is_404(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.VIEWER)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                with patch(
                    "app.api.v1.provider_connections.OrganizationRepository.get",
                    new=AsyncMock(return_value=None),
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.get(
                            f"/v1/organizations/{_ORG_ID}/provider-connections/scheduler/jobs"
                        )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()
