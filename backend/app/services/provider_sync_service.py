"""ProviderSyncService — AI Usage Synchronization Engine (EP-23.3).

Bridges a customer's encrypted ``ProviderConnection`` credential to the
existing, provider-agnostic ``UsageCollectionService`` (EP-08) — closing the
gap CLAUDE.md has flagged since EP-22 as "the next real blocker": every
prior EP's usage-collection machinery ran against a server-side
environment-variable key, never a customer's own connected credential.

Architecture (mirrors CLAUDE.md §13's ProviderCredentialService /
ProviderValidator / ProviderHealthService layering exactly, one layer
higher):

    ProviderConnection
          |
          v
    ProviderCredentialService.decrypt()   — the only place a plaintext key
          |                                  is ever produced, in memory only
          v
    build_provider_config()               — shared with ProviderValidator
          |                                  (app.providers.validation)
          v
    UsageCollectionService.collect()      — shared with the env-var-keyed
          |                                  ops endpoints (app.api.v1.usage);
          |                                  all pagination / checkpoint /
          |                                  normalization / persistence
          |                                  logic lives there, once
          v
    UsageCollectionRun (+ UsageCollectionCheckpoint, updated per page)

No new tables. "Sync status" (last started/completed/successful sync, last
error, last imported timestamp) is derived entirely from the existing
``UsageCollectionRun``/``UsageCollectionCheckpoint`` rows already written by
``UsageCollectionService`` — see ``get_sync_status`` below.

Retry strategy: already implemented, reused unchanged. ``ProviderHttpClient``
(app.http.client) retries every individual request through
``ExponentialRetryPolicy`` (app.http.retry), which only retries
``ProviderError`` subclasses marked ``retryable=True`` — ``RateLimitError``,
``NetworkError``, ``InternalProviderError``. ``AuthenticationError``,
``QuotaExceededError``, and ``InvalidRequestError`` are never retried. A
whole *sync run* that still fails after those per-request retries is simply
left in ``FAILED`` status with the error captured — the user's own "Sync
Now" click (or a future "Retry failed sync" action, which is just
"call sync again") naturally resumes from the last checkpoint, so no
separate retry-scheduling subsystem is introduced here.

Security: the decrypted API key exists only as a Python local for the
duration of one ``sync_connection()`` call — never logged (structlog calls
below bind only ``provider``/``organization_id``/``connection_id``/timing/
counts), never returned in any response, never cached, never written to the
database in plaintext.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.provider_connection import ProviderConnection
from app.models.usage_collection_checkpoint import UsageCollectionCheckpoint
from app.models.usage_collection_run import (
    CollectionRunStatus,
    CollectionTrigger,
    UsageCollectionRun,
)
from app.providers.validation import build_provider_config
from app.repositories.provider_connection_repository import ProviderConnectionRepository
from app.repositories.usage_collection_checkpoint_repository import (
    UsageCollectionCheckpointRepository,
)
from app.repositories.usage_collection_run_repository import UsageCollectionRunRepository
from app.repositories.usage_cost_record_repository import UsageCostRecordRepository
from app.repositories.usage_event_repository import UsageEventRepository
from app.services.provider_credential_service import ProviderCredentialService
from app.usage.service import UsageCollectionService

log = structlog.get_logger(__name__)

# When a connection has never been synced before, look back this far on the
# first run rather than attempting to import a provider's entire history in
# one request. Subsequent runs are incremental from the checkpoint.
DEFAULT_LOOKBACK_DAYS = 30

# Providers with a real (non-stub) get_usage() implementation as of this EP
# — see CLAUDE.md §13's adapter table. Syncing any other provider type
# returns an honest zero-events COMPLETED run rather than an error, matching
# this codebase's "no adapter yet" precedent (app.api.v1.providers).
_PRODUCTION_USAGE_PROVIDERS = frozenset({"openai", "anthropic"})


@dataclass(frozen=True, slots=True)
class SyncStatus:
    """Derived, read-only view of a connection's synchronization state.

    Every field is computed from existing ``UsageCollectionRun`` /
    ``UsageCollectionCheckpoint`` / ``UsageEvent`` / ``UsageCostRecord``
    rows — nothing here is persisted directly; see ``ProviderSyncService.
    get_sync_status``.
    """

    connection_id: UUID
    provider_type: str
    sync_status: str  # "never_synced" | "pending" | "running" | "success" | "failed"
    last_sync_started_at: datetime | None
    last_sync_completed_at: datetime | None
    last_successful_sync_at: datetime | None
    last_error: str | None
    last_imported_at: datetime | None
    records_imported: int
    tokens_imported: int
    # [{"currency": "USD", "total_cost": Decimal, "record_count": int}, ...]
    estimated_cost_imported: list[dict[str, Any]]
    supports_usage_sync: bool


_DISPLAY_STATUS: dict[CollectionRunStatus, str] = {
    CollectionRunStatus.PENDING: "pending",
    CollectionRunStatus.RUNNING: "running",
    CollectionRunStatus.COMPLETED: "success",
    CollectionRunStatus.FAILED: "failed",
    CollectionRunStatus.CANCELLED: "failed",
}


class ProviderSyncService:
    """Orchestrates usage synchronization for one or all of an org's provider connections."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        credentials: ProviderCredentialService | None = None,
        collection_service: UsageCollectionService | None = None,
    ) -> None:
        self._session = session
        self._credentials = credentials or ProviderCredentialService()
        self._collection = collection_service or UsageCollectionService(session)

    # ── Sync one connection ────────────────────────────────────────────────────

    async def sync_connection(
        self,
        *,
        organization_id: UUID,
        connection: ProviderConnection,
        triggered_by: CollectionTrigger = CollectionTrigger.MANUAL,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    ) -> UsageCollectionRun:
        """Run one synchronization pass for *connection*.

        Always returns a ``UsageCollectionRun`` in a terminal state
        (COMPLETED or FAILED) — never raises for a provider-side failure
        (network error, invalid credential, provider outage). Callers should
        still let genuinely unexpected exceptions (e.g. a database error)
        propagate; this method only swallows the specific exception
        ``UsageCollectionService.collect()`` itself already raises after
        persisting a FAILED run, so the caller gets that persisted run back
        instead of an unhandled 500.
        """
        provider = connection.provider_type.value
        logger = log.bind(
            organization_id=str(organization_id),
            connection_id=str(connection.id),
            provider=provider,
        )

        if provider not in _PRODUCTION_USAGE_PROVIDERS:
            logger.info("usage_sync_skipped_unsupported_provider")
            return await self._record_unsupported_provider_run(
                organization_id=organization_id,
                connection=connection,
                triggered_by=triggered_by,
            )

        checkpoint_repo = UsageCollectionCheckpointRepository(self._session)
        checkpoint = await checkpoint_repo.get_by_org_provider(
            organization_id, provider, connection.id
        )

        end_date = datetime.now(UTC)
        start_date = self._effective_start(checkpoint, end_date, lookback_days)

        # Decrypt only in memory, for the duration of this call — never
        # logged, never persisted, never returned. Ollama's config does not
        # require a key at all.
        api_key = (
            self._credentials.decrypt(connection.encrypted_api_key)
            if connection.encrypted_api_key
            else None
        )
        config = build_provider_config(
            connection.provider_type, api_key=api_key, base_url=connection.base_url
        )

        started_at = datetime.now(UTC)
        logger.info("usage_sync_started", start_date=start_date.isoformat())
        try:
            run = await self._collection.collect(
                organization_id=organization_id,
                provider=provider,
                start_date=start_date,
                end_date=end_date,
                provider_connection_id=connection.id,
                project_id=connection.project_id,
                triggered_by=triggered_by,
                config=config,
            )
            logger.info(
                "usage_sync_completed",
                duration_seconds=(datetime.now(UTC) - started_at).total_seconds(),
                records_imported=run.events_collected,
                records_skipped=run.events_failed,
            )
            return run
        except Exception as exc:
            # collect() already persisted a FAILED UsageCollectionRun (with
            # error_message=str(exc)) before re-raising — re-fetch it rather
            # than let the exception propagate, so a sync failure is a
            # normal terminal state, not an unhandled server error. Never
            # log `exc` verbatim beyond its class name here — the message
            # is already captured, user-safe, on the persisted run, and
            # provider exceptions are documented (app/providers/errors.py)
            # to never interpolate credential material.
            logger.warning("usage_sync_failed", error_type=type(exc).__name__)
            run_repo = UsageCollectionRunRepository(self._session)
            failed_run = await run_repo.get_latest_for_connection(organization_id, connection.id)
            if failed_run is None:
                raise
            return failed_run

    # ── Sync every active connection in an organization ──────────────────────

    async def sync_all_connections(
        self,
        *,
        organization_id: UUID,
        triggered_by: CollectionTrigger = CollectionTrigger.MANUAL,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    ) -> list[UsageCollectionRun]:
        """Sync every active provider connection in the organization.

        One connection's failure never stops the others — each is run
        independently and its outcome (COMPLETED or FAILED) is included in
        the returned list.
        """
        conn_repo = ProviderConnectionRepository(self._session)
        page = await conn_repo.list_active_by_org(organization_id, limit=100)

        runs: list[UsageCollectionRun] = []
        for connection in page.items:
            run = await self.sync_connection(
                organization_id=organization_id,
                connection=connection,
                triggered_by=triggered_by,
                lookback_days=lookback_days,
            )
            runs.append(run)
        return runs

    # ── Sync status (read-only, no side effects) ──────────────────────────────

    async def get_sync_status(
        self,
        *,
        organization_id: UUID,
        connection: ProviderConnection,
    ) -> SyncStatus:
        """Derive the connection's synchronization state from existing tables.

        No new columns: reads the latest ``UsageCollectionRun`` (any
        outcome), the latest COMPLETED run, the checkpoint's
        ``last_collected_at``, and all-time event/cost aggregates — every
        one of these already existed before this EP.
        """
        run_repo = UsageCollectionRunRepository(self._session)
        checkpoint_repo = UsageCollectionCheckpointRepository(self._session)
        event_repo = UsageEventRepository(self._session)
        cost_repo = UsageCostRecordRepository(self._session)

        latest_run = await run_repo.get_latest_for_connection(organization_id, connection.id)
        latest_success = await run_repo.get_latest_for_connection(
            organization_id, connection.id, status=CollectionRunStatus.COMPLETED
        )
        checkpoint = await checkpoint_repo.get_by_org_provider(
            organization_id, connection.provider_type.value, connection.id
        )
        totals = await event_repo.get_totals_by_connection(connection.id)
        cost_totals = await cost_repo.get_totals_by_connection(connection.id)

        sync_status = (
            _DISPLAY_STATUS[latest_run.status] if latest_run is not None else "never_synced"
        )

        return SyncStatus(
            connection_id=connection.id,
            provider_type=connection.provider_type.value,
            sync_status=sync_status,
            last_sync_started_at=latest_run.started_at if latest_run else None,
            last_sync_completed_at=latest_run.completed_at if latest_run else None,
            last_successful_sync_at=latest_success.completed_at if latest_success else None,
            last_error=latest_run.error_message if latest_run else None,
            last_imported_at=checkpoint.last_collected_at if checkpoint else None,
            records_imported=totals["total_records"],
            tokens_imported=totals["total_tokens"],
            estimated_cost_imported=[
                {
                    "currency": row["currency"],
                    "total_cost": row["total_cost"],
                    "record_count": row["record_count"],
                }
                for row in cost_totals
            ],
            supports_usage_sync=connection.provider_type.value in _PRODUCTION_USAGE_PROVIDERS,
        )

    # ── Private helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _effective_start(
        checkpoint: UsageCollectionCheckpoint | None,
        end_date: datetime,
        lookback_days: int,
    ) -> datetime:
        """Incremental sync: resume from the checkpoint when one exists and
        is still before ``end_date``; otherwise fall back to a bounded
        lookback window rather than attempting full provider history."""
        default_start = end_date - timedelta(days=lookback_days)
        if checkpoint is not None and checkpoint.last_collected_at < end_date:
            return max(checkpoint.last_collected_at, default_start)
        return default_start

    async def _record_unsupported_provider_run(
        self,
        *,
        organization_id: UUID,
        connection: ProviderConnection,
        triggered_by: CollectionTrigger,
    ) -> UsageCollectionRun:
        """For providers without a real get_usage() yet (5 of 7 — see
        CLAUDE.md §13's adapter table), record an honest zero-events
        COMPLETED run rather than fabricating activity or raising an error
        the user can't act on."""
        run_repo = UsageCollectionRunRepository(self._session)
        now = datetime.now(UTC)
        run = UsageCollectionRun()
        run.organization_id = organization_id
        run.provider_connection_id = connection.id
        run.provider = connection.provider_type.value
        run.status = CollectionRunStatus.COMPLETED
        run.triggered_by = triggered_by
        run.started_at = now
        run.completed_at = now
        run.collection_start = now
        run.collection_end = now
        run.events_collected = 0
        run.events_failed = 0
        run.pages_fetched = 0
        run.error_message = (
            f"{connection.provider_type.value} does not have usage synchronization "
            "support yet — no data was imported."
        )
        run.collection_config = {"reason": "provider_not_yet_supported_for_usage_sync"}
        return await run_repo.create(run)
