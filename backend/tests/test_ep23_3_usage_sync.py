"""Tests for the AI Usage Synchronization Engine (EP-23.3).

Covers:
  - ``ProviderSyncService.sync_connection`` — supported vs. unsupported
    provider, successful sync, failure re-fetch, incremental start-date logic
  - ``ProviderSyncService.sync_all_connections`` — mixed success/failure
    across an org's connections
  - ``ProviderSyncService.get_sync_status`` — derivation from existing
    UsageCollectionRun/Checkpoint/UsageEvent/UsageCostRecord rows only
  - API: GET .../sync-status, POST .../sync, POST .../provider-connections/sync
    (org-wide) — response shape, RBAC (PROVIDER_READ / PROVIDER_WRITE), and
    that no credential material ever appears in a response body

All tests are hermetic — no network calls, no real database. Provider HTTP
calls are never exercised here (that's ``test_ep22_provider_validator.py``'s
job); ``ProviderSyncService`` is tested by injecting mock
``ProviderCredentialService`` / ``UsageCollectionService`` collaborators and
patching the repository classes it instantiates internally.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.models.membership import Membership, MembershipRole
from app.models.organization import Organization, OrganizationStatus
from app.models.provider_connection import ProviderConnection, ProviderType
from app.models.usage_collection_checkpoint import UsageCollectionCheckpoint
from app.models.usage_collection_run import (
    CollectionRunStatus,
    CollectionTrigger,
    UsageCollectionRun,
)
from app.models.user import User
from app.services.provider_sync_service import (
    DEFAULT_LOOKBACK_DAYS,
    ProviderSyncService,
    SyncStatus,
)
from tests.conftest import make_provider_connection

_ORG_ID = uuid.uuid4()
_NOW = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)


def _make_session() -> MagicMock:
    session = MagicMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    return session


def _make_run(
    *,
    status: CollectionRunStatus = CollectionRunStatus.COMPLETED,
    provider: str = "openai",
    events_collected: int = 5,
    events_failed: int = 0,
    error_message: str | None = None,
    connection_id: uuid.UUID | None = None,
) -> UsageCollectionRun:
    from app.db.mixins import uuid7

    run = UsageCollectionRun()
    run.id = uuid7()
    run.organization_id = _ORG_ID
    run.provider_connection_id = connection_id
    run.provider = provider
    run.status = status
    run.triggered_by = CollectionTrigger.MANUAL
    run.started_at = _NOW
    run.completed_at = _NOW if status != CollectionRunStatus.RUNNING else None
    run.collection_start = _NOW - timedelta(days=1)
    run.collection_end = _NOW
    run.events_collected = events_collected
    run.events_failed = events_failed
    run.pages_fetched = 1
    run.error_message = error_message
    run.collection_config = {}
    run.created_at = _NOW
    run.updated_at = _NOW
    return run


# ══════════════════════════════════════════════════════════════════════════════
# ProviderSyncService.sync_connection
# ══════════════════════════════════════════════════════════════════════════════


class TestSyncConnection:
    @pytest.mark.asyncio
    async def test_provider_without_usage_api_still_goes_through_real_pipeline(self) -> None:
        """EP-24.3: a provider whose adapter has no bulk usage-history API
        (e.g. Ollama) no longer takes a skip/shortcut — it goes through the
        exact same `UsageCollectionService.collect()` call every other
        provider does. The adapter's own `get_usage()` is what honestly
        returns zero events; `sync_connection()` itself no longer special-
        cases any provider type."""
        conn = make_provider_connection(org_id=_ORG_ID, provider_type=ProviderType.OLLAMA)
        session = _make_session()
        mock_credentials = MagicMock()

        completed_run = _make_run(
            status=CollectionRunStatus.COMPLETED,
            provider="ollama",
            events_collected=0,
            connection_id=conn.id,
        )
        mock_collection = AsyncMock()
        mock_collection.collect.return_value = completed_run

        mock_checkpoint_repo = AsyncMock()
        mock_checkpoint_repo.get_by_org_provider.return_value = None

        with (
            patch(
                "app.services.provider_sync_service.UsageCollectionCheckpointRepository",
                return_value=mock_checkpoint_repo,
            ),
            patch(
                "app.services.provider_sync_service.build_provider_config", return_value=MagicMock()
            ) as build_config_mock,
        ):
            service = ProviderSyncService(
                session, credentials=mock_credentials, collection_service=mock_collection
            )
            run = await service.sync_connection(organization_id=_ORG_ID, connection=conn)

        assert run is completed_run
        assert run.status == CollectionRunStatus.COMPLETED
        assert run.events_collected == 0
        build_config_mock.assert_called_once()
        mock_collection.collect.assert_awaited_once()
        call_kwargs = mock_collection.collect.call_args.kwargs
        assert call_kwargs["provider"] == "ollama"

    @pytest.mark.asyncio
    async def test_supported_provider_success_calls_collect_with_decrypted_config(self) -> None:
        conn = make_provider_connection(
            org_id=_ORG_ID,
            provider_type=ProviderType.OPENAI,
            encrypted_api_key="v1:ciphertext",
        )
        session = _make_session()

        mock_credentials = MagicMock()
        mock_credentials.decrypt.return_value = "sk-plaintext-key"

        completed_run = _make_run(status=CollectionRunStatus.COMPLETED, connection_id=conn.id)
        mock_collection = AsyncMock()
        mock_collection.collect.return_value = completed_run

        mock_checkpoint_repo = AsyncMock()
        mock_checkpoint_repo.get_by_org_provider.return_value = None

        with (
            patch(
                "app.services.provider_sync_service.UsageCollectionCheckpointRepository",
                return_value=mock_checkpoint_repo,
            ),
            patch(
                "app.services.provider_sync_service.build_provider_config", return_value=MagicMock()
            ) as build_config_mock,
        ):
            service = ProviderSyncService(
                session, credentials=mock_credentials, collection_service=mock_collection
            )
            run = await service.sync_connection(organization_id=_ORG_ID, connection=conn)

        assert run is completed_run
        mock_credentials.decrypt.assert_called_once_with("v1:ciphertext")
        build_config_mock.assert_called_once()
        mock_collection.collect.assert_awaited_once()
        call_kwargs = mock_collection.collect.call_args.kwargs
        assert call_kwargs["organization_id"] == _ORG_ID
        assert call_kwargs["provider"] == "openai"
        assert call_kwargs["provider_connection_id"] == conn.id
        assert call_kwargs["config"] is not None

    @pytest.mark.asyncio
    async def test_ollama_has_no_credential_never_decrypted(self) -> None:
        """Ollama's config does not require a key — connection.encrypted_api_key
        is None, so decrypt() must never be called (it would fail on None)."""
        conn = make_provider_connection(
            org_id=_ORG_ID, provider_type=ProviderType.OLLAMA, encrypted_api_key=None
        )
        session = _make_session()
        mock_credentials = MagicMock()
        mock_collection = AsyncMock()
        mock_collection.collect.return_value = _make_run(provider="ollama", connection_id=conn.id)

        mock_checkpoint_repo = AsyncMock()
        mock_checkpoint_repo.get_by_org_provider.return_value = None

        with (
            patch(
                "app.services.provider_sync_service.UsageCollectionCheckpointRepository",
                return_value=mock_checkpoint_repo,
            ),
            patch(
                "app.services.provider_sync_service.build_provider_config", return_value=MagicMock()
            ),
        ):
            service = ProviderSyncService(
                session, credentials=mock_credentials, collection_service=mock_collection
            )
            await service.sync_connection(organization_id=_ORG_ID, connection=conn)

        mock_credentials.decrypt.assert_not_called()

    @pytest.mark.asyncio
    async def test_failure_re_fetches_persisted_failed_run_instead_of_raising(self) -> None:
        """UsageCollectionService.collect() persists a FAILED run then
        re-raises (EP-08's existing contract) — sync_connection must catch
        that, re-fetch the FAILED run, and return it as a normal terminal
        state rather than letting a 500 escape to the API layer."""
        conn = make_provider_connection(
            org_id=_ORG_ID,
            provider_type=ProviderType.ANTHROPIC,
            encrypted_api_key="v1:ciphertext",
        )
        session = _make_session()

        mock_credentials = MagicMock()
        mock_credentials.decrypt.return_value = "sk-ant-plaintext"

        mock_collection = AsyncMock()
        mock_collection.collect.side_effect = RuntimeError("provider unreachable")

        failed_run = _make_run(
            status=CollectionRunStatus.FAILED,
            provider="anthropic",
            events_collected=0,
            error_message="Network error",
            connection_id=conn.id,
        )
        mock_run_repo = AsyncMock()
        mock_run_repo.get_latest_for_connection.return_value = failed_run

        mock_checkpoint_repo = AsyncMock()
        mock_checkpoint_repo.get_by_org_provider.return_value = None

        with (
            patch(
                "app.services.provider_sync_service.UsageCollectionRunRepository",
                return_value=mock_run_repo,
            ),
            patch(
                "app.services.provider_sync_service.UsageCollectionCheckpointRepository",
                return_value=mock_checkpoint_repo,
            ),
            patch(
                "app.services.provider_sync_service.build_provider_config",
                return_value=MagicMock(),
            ),
        ):
            service = ProviderSyncService(
                session, credentials=mock_credentials, collection_service=mock_collection
            )
            run = await service.sync_connection(organization_id=_ORG_ID, connection=conn)

        assert run is failed_run
        assert run.status == CollectionRunStatus.FAILED
        mock_run_repo.get_latest_for_connection.assert_awaited_once_with(_ORG_ID, conn.id)

    @pytest.mark.asyncio
    async def test_failure_reraises_when_no_run_can_be_found(self) -> None:
        """If, unexpectedly, no FAILED run exists to re-fetch, the original
        exception must propagate rather than being silently swallowed."""
        conn = make_provider_connection(
            org_id=_ORG_ID, provider_type=ProviderType.OPENAI, encrypted_api_key="v1:x"
        )
        session = _make_session()
        mock_credentials = MagicMock()
        mock_credentials.decrypt.return_value = "sk-x"
        mock_collection = AsyncMock()
        mock_collection.collect.side_effect = RuntimeError("boom")

        mock_run_repo = AsyncMock()
        mock_run_repo.get_latest_for_connection.return_value = None
        mock_checkpoint_repo = AsyncMock()
        mock_checkpoint_repo.get_by_org_provider.return_value = None

        with (
            patch(
                "app.services.provider_sync_service.UsageCollectionRunRepository",
                return_value=mock_run_repo,
            ),
            patch(
                "app.services.provider_sync_service.UsageCollectionCheckpointRepository",
                return_value=mock_checkpoint_repo,
            ),
            patch(
                "app.services.provider_sync_service.build_provider_config",
                return_value=MagicMock(),
            ),
        ):
            service = ProviderSyncService(
                session, credentials=mock_credentials, collection_service=mock_collection
            )
            with pytest.raises(RuntimeError, match="boom"):
                await service.sync_connection(organization_id=_ORG_ID, connection=conn)

    def test_effective_start_no_checkpoint_uses_lookback(self) -> None:
        end = _NOW
        start = ProviderSyncService._effective_start(None, end, DEFAULT_LOOKBACK_DAYS)
        assert start == end - timedelta(days=DEFAULT_LOOKBACK_DAYS)

    def test_effective_start_resumes_from_recent_checkpoint(self) -> None:
        end = _NOW
        checkpoint = UsageCollectionCheckpoint()
        checkpoint.last_collected_at = end - timedelta(days=2)
        start = ProviderSyncService._effective_start(checkpoint, end, DEFAULT_LOOKBACK_DAYS)
        assert start == checkpoint.last_collected_at

    def test_effective_start_ignores_stale_checkpoint_beyond_lookback(self) -> None:
        """A checkpoint older than the lookback window still bounds the
        query to the lookback window, not the provider's entire history."""
        end = _NOW
        checkpoint = UsageCollectionCheckpoint()
        checkpoint.last_collected_at = end - timedelta(days=90)
        start = ProviderSyncService._effective_start(checkpoint, end, DEFAULT_LOOKBACK_DAYS)
        assert start == end - timedelta(days=DEFAULT_LOOKBACK_DAYS)

    def test_effective_start_checkpoint_in_future_falls_back_to_lookback(self) -> None:
        end = _NOW
        checkpoint = UsageCollectionCheckpoint()
        checkpoint.last_collected_at = end + timedelta(days=1)
        start = ProviderSyncService._effective_start(checkpoint, end, DEFAULT_LOOKBACK_DAYS)
        assert start == end - timedelta(days=DEFAULT_LOOKBACK_DAYS)


# ══════════════════════════════════════════════════════════════════════════════
# ProviderSyncService.sync_all_connections
# ══════════════════════════════════════════════════════════════════════════════


class TestSyncAllConnections:
    @pytest.mark.asyncio
    async def test_one_failure_does_not_stop_others(self) -> None:
        conn_ok = make_provider_connection(
            org_id=_ORG_ID, provider_type=ProviderType.OPENAI, encrypted_api_key="v1:a"
        )
        conn_fail = make_provider_connection(
            org_id=_ORG_ID, provider_type=ProviderType.ANTHROPIC, encrypted_api_key="v1:b"
        )
        session = _make_session()

        page = MagicMock()
        page.items = [conn_ok, conn_fail]
        mock_conn_repo = AsyncMock()
        mock_conn_repo.list_active_by_org.return_value = page

        service = ProviderSyncService(session)

        ok_run = _make_run(status=CollectionRunStatus.COMPLETED, connection_id=conn_ok.id)
        fail_run = _make_run(
            status=CollectionRunStatus.FAILED,
            connection_id=conn_fail.id,
            error_message="boom",
        )

        async def fake_sync_connection(
            *, organization_id: uuid.UUID, connection: ProviderConnection, **_: Any
        ) -> UsageCollectionRun:
            return ok_run if connection.id == conn_ok.id else fail_run

        with (
            patch(
                "app.services.provider_sync_service.ProviderConnectionRepository",
                return_value=mock_conn_repo,
            ),
            patch.object(service, "sync_connection", side_effect=fake_sync_connection),
        ):
            runs = await service.sync_all_connections(organization_id=_ORG_ID)

        assert len(runs) == 2
        assert runs[0] is ok_run
        assert runs[1] is fail_run

    @pytest.mark.asyncio
    async def test_no_active_connections_returns_empty_list(self) -> None:
        session = _make_session()
        page = MagicMock()
        page.items = []
        mock_conn_repo = AsyncMock()
        mock_conn_repo.list_active_by_org.return_value = page

        with patch(
            "app.services.provider_sync_service.ProviderConnectionRepository",
            return_value=mock_conn_repo,
        ):
            service = ProviderSyncService(session)
            runs = await service.sync_all_connections(organization_id=_ORG_ID)

        assert runs == []


# ══════════════════════════════════════════════════════════════════════════════
# ProviderSyncService.get_sync_status
# ══════════════════════════════════════════════════════════════════════════════


class TestGetSyncStatus:
    @pytest.mark.asyncio
    async def test_never_synced_connection(self) -> None:
        conn = make_provider_connection(org_id=_ORG_ID, provider_type=ProviderType.OPENAI)
        session = _make_session()

        mock_run_repo = AsyncMock()
        mock_run_repo.get_latest_for_connection.return_value = None
        mock_checkpoint_repo = AsyncMock()
        mock_checkpoint_repo.get_by_org_provider.return_value = None
        mock_event_repo = AsyncMock()
        mock_event_repo.get_totals_by_connection.return_value = {
            "total_records": 0,
            "total_tokens": 0,
        }
        mock_cost_repo = AsyncMock()
        mock_cost_repo.get_totals_by_connection.return_value = []

        with (
            patch(
                "app.services.provider_sync_service.UsageCollectionRunRepository",
                return_value=mock_run_repo,
            ),
            patch(
                "app.services.provider_sync_service.UsageCollectionCheckpointRepository",
                return_value=mock_checkpoint_repo,
            ),
            patch(
                "app.services.provider_sync_service.UsageEventRepository",
                return_value=mock_event_repo,
            ),
            patch(
                "app.services.provider_sync_service.UsageCostRecordRepository",
                return_value=mock_cost_repo,
            ),
        ):
            service = ProviderSyncService(session)
            status = await service.get_sync_status(organization_id=_ORG_ID, connection=conn)

        assert isinstance(status, SyncStatus)
        assert status.sync_status == "never_synced"
        assert status.last_sync_started_at is None
        assert status.records_imported == 0
        assert status.supports_usage_sync is True

    @pytest.mark.asyncio
    async def test_derives_success_state_and_totals(self) -> None:
        conn = make_provider_connection(org_id=_ORG_ID, provider_type=ProviderType.OPENAI)
        session = _make_session()

        latest_run = _make_run(status=CollectionRunStatus.COMPLETED, connection_id=conn.id)
        mock_run_repo = AsyncMock()
        mock_run_repo.get_latest_for_connection.side_effect = [latest_run, latest_run]

        checkpoint = UsageCollectionCheckpoint()
        checkpoint.last_collected_at = _NOW
        mock_checkpoint_repo = AsyncMock()
        mock_checkpoint_repo.get_by_org_provider.return_value = checkpoint

        mock_event_repo = AsyncMock()
        mock_event_repo.get_totals_by_connection.return_value = {
            "total_records": 42,
            "total_tokens": 12345,
        }
        mock_cost_repo = AsyncMock()
        mock_cost_repo.get_totals_by_connection.return_value = [
            {"currency": "USD", "total_cost": 1.23, "record_count": 42}
        ]

        with (
            patch(
                "app.services.provider_sync_service.UsageCollectionRunRepository",
                return_value=mock_run_repo,
            ),
            patch(
                "app.services.provider_sync_service.UsageCollectionCheckpointRepository",
                return_value=mock_checkpoint_repo,
            ),
            patch(
                "app.services.provider_sync_service.UsageEventRepository",
                return_value=mock_event_repo,
            ),
            patch(
                "app.services.provider_sync_service.UsageCostRecordRepository",
                return_value=mock_cost_repo,
            ),
        ):
            service = ProviderSyncService(session)
            status = await service.get_sync_status(organization_id=_ORG_ID, connection=conn)

        assert status.sync_status == "success"
        assert status.last_successful_sync_at == latest_run.completed_at
        assert status.last_imported_at == _NOW
        assert status.records_imported == 42
        assert status.tokens_imported == 12345
        assert status.estimated_cost_imported == [
            {"currency": "USD", "total_cost": 1.23, "record_count": 42}
        ]
        assert status.estimated_cost_imported[0]["record_count"] == 42

    @pytest.mark.asyncio
    async def test_provider_without_usage_api_flagged_in_status(self) -> None:
        """`supports_usage_sync` (EP-24.3: purely informational — never
        gates whether sync runs) is False for a provider with no known
        bulk usage-history API, even though sync itself executes fine."""
        conn = make_provider_connection(org_id=_ORG_ID, provider_type=ProviderType.OLLAMA)
        session = _make_session()

        mock_run_repo = AsyncMock()
        mock_run_repo.get_latest_for_connection.return_value = None
        mock_checkpoint_repo = AsyncMock()
        mock_checkpoint_repo.get_by_org_provider.return_value = None
        mock_event_repo = AsyncMock()
        mock_event_repo.get_totals_by_connection.return_value = {
            "total_records": 0,
            "total_tokens": 0,
        }
        mock_cost_repo = AsyncMock()
        mock_cost_repo.get_totals_by_connection.return_value = []

        with (
            patch(
                "app.services.provider_sync_service.UsageCollectionRunRepository",
                return_value=mock_run_repo,
            ),
            patch(
                "app.services.provider_sync_service.UsageCollectionCheckpointRepository",
                return_value=mock_checkpoint_repo,
            ),
            patch(
                "app.services.provider_sync_service.UsageEventRepository",
                return_value=mock_event_repo,
            ),
            patch(
                "app.services.provider_sync_service.UsageCostRecordRepository",
                return_value=mock_cost_repo,
            ),
        ):
            service = ProviderSyncService(session)
            status = await service.get_sync_status(organization_id=_ORG_ID, connection=conn)

        assert status.supports_usage_sync is False


# ══════════════════════════════════════════════════════════════════════════════
# API: GET/POST .../provider-connections/{id}/sync[-status], POST .../sync
# ══════════════════════════════════════════════════════════════════════════════


def _timestamped(conn: ProviderConnection) -> ProviderConnection:
    conn.created_at = datetime.now(UTC)
    conn.updated_at = datetime.now(UTC)
    return conn


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


def _sample_status(conn: ProviderConnection) -> SyncStatus:
    return SyncStatus(
        connection_id=conn.id,
        provider_type=conn.provider_type.value,
        sync_status="success",
        last_sync_started_at=_NOW,
        last_sync_completed_at=_NOW,
        last_successful_sync_at=_NOW,
        last_error=None,
        last_imported_at=_NOW,
        records_imported=10,
        tokens_imported=1000,
        estimated_cost_imported=[{"currency": "USD", "total_cost": 0.5, "record_count": 10}],
        supports_usage_sync=True,
    )


class TestSyncStatusEndpoint:
    @pytest.mark.asyncio
    async def test_unauthenticated_is_401(self, app: Any) -> None:
        conn_id = uuid.uuid4()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get(
                f"/v1/organizations/{_ORG_ID}/provider-connections/{conn_id}/sync-status"
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_viewer_can_read_sync_status(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.VIEWER)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                conn = _timestamped(
                    make_provider_connection(org_id=_ORG_ID, provider_type=ProviderType.OPENAI)
                )
                with (
                    patch(
                        "app.api.v1.provider_connections.ProviderConnectionRepository.get",
                        new=AsyncMock(return_value=conn),
                    ),
                    patch(
                        "app.services.provider_sync_service.ProviderSyncService.get_sync_status",
                        new=AsyncMock(return_value=_sample_status(conn)),
                    ),
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.get(
                            f"/v1/organizations/{_ORG_ID}/provider-connections/"
                            f"{conn.id}/sync-status"
                        )
            assert resp.status_code == 200
            body = resp.json()
            assert body["sync_status"] == "success"
            assert body["records_imported"] == 10
            assert body["tokens_imported"] == 1000
            assert body["estimated_cost_imported"][0]["currency"] == "USD"
            assert body["supports_usage_sync"] is True
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_unknown_connection_is_404(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.VIEWER)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                with patch(
                    "app.api.v1.provider_connections.ProviderConnectionRepository.get",
                    new=AsyncMock(return_value=None),
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.get(
                            f"/v1/organizations/{_ORG_ID}/provider-connections/"
                            f"{uuid.uuid4()}/sync-status"
                        )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()


class TestSyncConnectionEndpoint:
    @pytest.mark.asyncio
    async def test_admin_can_trigger_sync(self, app: Any) -> None:
        """PROVIDER_WRITE is ADMIN+OWNER only (CLAUDE.md §13) — MEMBER has
        PROVIDER_READ but not WRITE, matching the existing test/rotate
        endpoints' RBAC boundary."""
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.ADMIN)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                conn = _timestamped(
                    make_provider_connection(
                        org_id=_ORG_ID,
                        provider_type=ProviderType.OPENAI,
                        encrypted_api_key="v1:ciphertext",
                    )
                )
                completed_run = _make_run(
                    status=CollectionRunStatus.COMPLETED, connection_id=conn.id
                )
                with (
                    patch(
                        "app.api.v1.provider_connections.ProviderConnectionRepository.get",
                        new=AsyncMock(return_value=conn),
                    ),
                    patch(
                        "app.services.provider_sync_service.ProviderSyncService.sync_connection",
                        new=AsyncMock(return_value=completed_run),
                    ),
                    patch(
                        "app.services.provider_sync_service.ProviderSyncService.get_sync_status",
                        new=AsyncMock(return_value=_sample_status(conn)),
                    ),
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.post(
                            f"/v1/organizations/{_ORG_ID}/provider-connections/{conn.id}/sync"
                        )
            assert resp.status_code == 200
            body = resp.json()
            assert body["run"]["status"] == "completed"
            assert body["run"]["records_imported"] == 5
            assert body["sync_status"]["sync_status"] == "success"
            # No credential material anywhere in the response.
            assert "ciphertext" not in resp.text
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_viewer_cannot_trigger_sync(self, app: Any) -> None:
        """PROVIDER_WRITE is required — VIEWER only has PROVIDER_READ."""
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
                    resp = await ac.post(
                        f"/v1/organizations/{_ORG_ID}/provider-connections/" f"{uuid.uuid4()}/sync"
                    )
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_member_cannot_trigger_sync(self, app: Any) -> None:
        """MEMBER has PROVIDER_READ but not PROVIDER_WRITE (ADMIN+OWNER only)."""
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
                    resp = await ac.post(
                        f"/v1/organizations/{_ORG_ID}/provider-connections/" f"{uuid.uuid4()}/sync"
                    )
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()


class TestSyncAllConnectionsEndpoint:
    @pytest.mark.asyncio
    async def test_admin_can_trigger_sync_all(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.ADMIN)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                conn1 = _timestamped(
                    make_provider_connection(org_id=_ORG_ID, provider_type=ProviderType.OPENAI)
                )
                conn2 = _timestamped(
                    make_provider_connection(org_id=_ORG_ID, provider_type=ProviderType.ANTHROPIC)
                )
                run1 = _make_run(status=CollectionRunStatus.COMPLETED, connection_id=conn1.id)
                run2 = _make_run(
                    status=CollectionRunStatus.FAILED,
                    connection_id=conn2.id,
                    error_message="Network error",
                    events_collected=0,
                )

                async def fake_get(connection_id: uuid.UUID) -> ProviderConnection | None:
                    if connection_id == conn1.id:
                        return conn1
                    if connection_id == conn2.id:
                        return conn2
                    return None

                with (
                    patch(
                        "app.services.provider_sync_service.ProviderSyncService"
                        ".sync_all_connections",
                        new=AsyncMock(return_value=[run1, run2]),
                    ),
                    patch(
                        "app.api.v1.provider_connections.ProviderConnectionRepository.get",
                        new=AsyncMock(side_effect=fake_get),
                    ),
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.post(
                            f"/v1/organizations/{_ORG_ID}/provider-connections/sync"
                        )
            assert resp.status_code == 200
            body = resp.json()
            assert body["total"] == 2
            assert body["succeeded"] == 1
            assert body["failed"] == 1
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_member_cannot_trigger_sync_all_without_write(self, app: Any) -> None:
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
                    resp = await ac.post(f"/v1/organizations/{_ORG_ID}/provider-connections/sync")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()
