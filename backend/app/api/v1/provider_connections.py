"""Provider Connections API — EP-22.

Endpoints:
  GET    /v1/organizations/{org_id}/provider-connections                 — list
  POST   /v1/organizations/{org_id}/provider-connections                 — create (+ validate)
  PATCH  /v1/organizations/{org_id}/provider-connections/{conn_id}       — update metadata
  DELETE /v1/organizations/{org_id}/provider-connections/{conn_id}       — soft-delete
  POST   /v1/organizations/{org_id}/provider-connections/{conn_id}/test  — re-run validation
  POST   /v1/organizations/{org_id}/provider-connections/{conn_id}/rotate — replace the API key
  GET    /v1/organizations/{org_id}/provider-connections/{conn_id}/sync-status — EP-23.3
  POST   /v1/organizations/{org_id}/provider-connections/{conn_id}/sync        — EP-23.3
  POST   /v1/organizations/{org_id}/provider-connections/sync                  — EP-23.3
  GET    /v1/organizations/{org_id}/provider-connections/scheduler/status      — EP-23.4
  PATCH  /v1/organizations/{org_id}/provider-connections/scheduler/settings    — EP-23.4
  GET    /v1/organizations/{org_id}/provider-connections/scheduler/jobs        — EP-23.4

Authorization: PROVIDER_READ / PROVIDER_WRITE / PROVIDER_DELETE — all
already defined in app.auth.rbac (EP-13), no changes needed.

As of EP-22, a connection can hold a real, per-connection, encrypted API
key (``ProviderConnection.encrypted_api_key``) — see
``app.security.encryption.EncryptionService`` for how it's encrypted at
rest and ``app.providers.validation.ProviderValidator`` for how it's
validated live against the provider. No response in this router ever
serializes the decrypted key — see ``_to_response``'s use of
``ProviderCredentialService.masked``. Full architecture: CLAUDE.md §13.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, status

from app.api.deps import DbDep, SchedulerDep
from app.auth.dependencies import RequirePermission
from app.auth.rbac import Permission
from app.db.mixins import uuid7
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.provider_connection import ProviderConnection, ProviderType
from app.models.usage_collection_run import UsageCollectionRun
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.provider_connection_repository import ProviderConnectionRepository
from app.schemas.provider_connections import (
    CostImportedItem,
    CreateProviderConnectionRequest,
    ProviderConnectionResponse,
    ProviderConnectionsListResponse,
    RotateProviderConnectionKeyRequest,
    SchedulerJobItem,
    SchedulerJobsResponse,
    SchedulerMonitoringSnapshot,
    SchedulerStatusResponse,
    SyncAllResponse,
    SyncRunResponse,
    SyncStatusResponse,
    TestProviderConnectionResponse,
    TriggerSyncResponse,
    UpdateProviderConnectionRequest,
    UpdateSchedulerSettingsRequest,
)
from app.services.provider_credential_service import ProviderCredentialService
from app.services.provider_health_service import ProviderHealthService
from app.services.provider_sync_service import ProviderSyncService, SyncStatus
from app.services.usage_sync_scheduler import (
    INTERVAL_PRESETS,
    SchedulerJobRecord,
    SchedulerOrgStatus,
    interval_label_for,
)

router = APIRouter(
    prefix="/organizations/{org_id}/provider-connections", tags=["provider-connections"]
)

_credentials = ProviderCredentialService()
_health = ProviderHealthService()


def _parse_provider_type(value: str) -> ProviderType:
    try:
        return ProviderType(value)
    except ValueError as exc:
        supported = [p.value for p in ProviderType]
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid provider_type {value!r}. Must be one of: {supported}",
        ) from exc


def _to_response(conn: ProviderConnection) -> ProviderConnectionResponse:
    return ProviderConnectionResponse(
        id=conn.external_id,
        provider_type=conn.provider_type.value,
        display_name=conn.display_name,
        project_id=str(conn.project_id) if conn.project_id else None,
        is_active=conn.is_active,
        has_credential=conn.encrypted_api_key is not None,
        masked_api_key=_credentials.masked(conn.encrypted_api_key),
        base_url=conn.base_url,
        health_status=conn.health_status.value,
        last_validation_status=(
            conn.last_validation_status.value if conn.last_validation_status else None
        ),
        last_error=conn.last_error,
        last_failure_at=conn.last_failure_at,
        last_recovery_at=conn.last_recovery_at,
        consecutive_failure_count=conn.consecutive_failure_count,
        created_at=conn.created_at,
        updated_at=conn.updated_at,
    )


def _to_run_response(run: UsageCollectionRun, conn: ProviderConnection) -> SyncRunResponse:
    return SyncRunResponse(
        run_id=run.external_id,
        connection_id=conn.external_id,
        provider_type=run.provider,
        status=run.status.value,
        started_at=run.started_at,
        completed_at=run.completed_at,
        records_imported=run.events_collected,
        records_failed=run.events_failed,
        error_message=run.error_message,
    )


def _to_sync_status_response(
    sync_status: SyncStatus, conn: ProviderConnection
) -> SyncStatusResponse:
    return SyncStatusResponse(
        connection_id=conn.external_id,
        provider_type=sync_status.provider_type,
        sync_status=sync_status.sync_status,
        last_sync_started_at=sync_status.last_sync_started_at,
        last_sync_completed_at=sync_status.last_sync_completed_at,
        last_successful_sync_at=sync_status.last_successful_sync_at,
        last_error=sync_status.last_error,
        last_imported_at=sync_status.last_imported_at,
        records_imported=sync_status.records_imported,
        tokens_imported=sync_status.tokens_imported,
        estimated_cost_imported=[
            CostImportedItem(
                currency=item["currency"],
                total_cost=str(item["total_cost"]),
                record_count=item["record_count"],
            )
            for item in sync_status.estimated_cost_imported
        ],
        supports_usage_sync=sync_status.supports_usage_sync,
    )


async def _get_owned_connection(
    repo: ProviderConnectionRepository, org_id: uuid.UUID, connection_id: uuid.UUID
) -> ProviderConnection:
    conn = await repo.get(connection_id)
    if conn is None or conn.organization_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Provider connection not found"
        )
    return conn


@router.get(
    "",
    response_model=ProviderConnectionsListResponse,
    summary="List provider connections in an organization",
)
async def list_provider_connections(
    org_id: uuid.UUID,
    db: DbDep,
    _member: Annotated[Membership, RequirePermission(Permission.PROVIDER_READ)],
) -> ProviderConnectionsListResponse:
    repo = ProviderConnectionRepository(db)
    page = await repo.list_by_org(org_id, limit=100)
    return ProviderConnectionsListResponse(
        connections=[_to_response(c) for c in page.items],
        total=len(page.items),
    )


@router.post(
    "",
    response_model=ProviderConnectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a provider connection",
)
async def create_provider_connection(
    org_id: uuid.UUID,
    body: CreateProviderConnectionRequest,
    db: DbDep,
    _member: Annotated[Membership, RequirePermission(Permission.PROVIDER_WRITE)],
) -> ProviderConnectionResponse:
    pt = _parse_provider_type(body.provider_type)

    conn = ProviderConnection()
    conn.id = uuid7()
    conn.organization_id = org_id
    conn.provider_type = pt
    conn.provider_name = body.provider_type
    conn.display_name = body.display_name
    conn.project_id = body.project_id
    conn.base_url = body.base_url
    conn.is_active = True
    conn.configuration = {}
    conn.encrypted_api_key = _credentials.encrypt(body.api_key) if body.api_key else None

    repo = ProviderConnectionRepository(db)
    created = await repo.create(conn)

    # EP-22 Part 3: validate immediately on save, whenever there's something
    # to validate (a credential, or a no-credential-required provider like
    # Ollama) — a freshly created connection should never sit at "unknown"
    # when we could have told the user right away whether it works.
    if body.api_key or pt == ProviderType.OLLAMA:
        await _health.check_and_persist(
            repo, created, api_key=body.api_key, base_url=created.base_url
        )

    return _to_response(created)


@router.patch(
    "/{connection_id}",
    response_model=ProviderConnectionResponse,
    summary="Update a provider connection's metadata",
)
async def update_provider_connection(
    org_id: uuid.UUID,
    connection_id: uuid.UUID,
    body: UpdateProviderConnectionRequest,
    db: DbDep,
    _member: Annotated[Membership, RequirePermission(Permission.PROVIDER_WRITE)],
) -> ProviderConnectionResponse:
    repo = ProviderConnectionRepository(db)
    conn = await _get_owned_connection(repo, org_id, connection_id)

    updates = body.model_dump(exclude_unset=True)
    updated = await repo.update(conn, **updates) if updates else conn
    return _to_response(updated)


@router.delete(
    "/{connection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a provider connection",
)
async def delete_provider_connection(
    org_id: uuid.UUID,
    connection_id: uuid.UUID,
    db: DbDep,
    _member: Annotated[Membership, RequirePermission(Permission.PROVIDER_DELETE)],
) -> None:
    repo = ProviderConnectionRepository(db)
    conn = await _get_owned_connection(repo, org_id, connection_id)
    await repo.soft_delete(conn)


@router.post(
    "/{connection_id}/test",
    response_model=TestProviderConnectionResponse,
    summary="Test a provider connection (live validation)",
    description=(
        "Decrypts this connection's stored credential (if any) and runs a live "
        "validation call against the provider (EP-22 Part 3 — see the per-provider "
        "probe endpoint table in CLAUDE.md §13), persisting the result onto "
        "health_status / last_validation_status / last_error / "
        "last_failure_at / last_recovery_at / consecutive_failure_count."
    ),
)
async def test_provider_connection(
    org_id: uuid.UUID,
    connection_id: uuid.UUID,
    db: DbDep,
    _member: Annotated[Membership, RequirePermission(Permission.PROVIDER_WRITE)],
) -> TestProviderConnectionResponse:
    repo = ProviderConnectionRepository(db)
    conn = await _get_owned_connection(repo, org_id, connection_id)

    api_key = _credentials.decrypt(conn.encrypted_api_key) if conn.encrypted_api_key else None
    result = await _health.check_and_persist(repo, conn, api_key=api_key, base_url=conn.base_url)

    return TestProviderConnectionResponse(
        connection_id=conn.external_id,
        provider_type=conn.provider_type.value,
        health_status=result.health_status.value,
        last_validation_status=result.validation_status.value,
        tested=True,
        detail=result.detail,
    )


@router.post(
    "/{connection_id}/rotate",
    response_model=ProviderConnectionResponse,
    summary="Rotate a provider connection's API key",
    description=(
        "Replaces the stored credential and immediately re-validates it. The "
        "previous key is never returned or logged — only its encrypted form is "
        "overwritten. updated_at (and, once validation completes, "
        "last_recovery_at/last_failure_at) record the rotation for audit purposes."
    ),
)
async def rotate_provider_connection_key(
    org_id: uuid.UUID,
    connection_id: uuid.UUID,
    body: RotateProviderConnectionKeyRequest,
    db: DbDep,
    _member: Annotated[Membership, RequirePermission(Permission.PROVIDER_WRITE)],
) -> ProviderConnectionResponse:
    repo = ProviderConnectionRepository(db)
    conn = await _get_owned_connection(repo, org_id, connection_id)

    updated = await repo.update(conn, encrypted_api_key=_credentials.encrypt(body.api_key))
    await _health.check_and_persist(repo, updated, api_key=body.api_key, base_url=updated.base_url)
    return _to_response(updated)


@router.get(
    "/{connection_id}/sync-status",
    response_model=SyncStatusResponse,
    summary="Get a provider connection's usage synchronization status",
    description=(
        "Derived entirely from existing UsageCollectionRun / "
        "UsageCollectionCheckpoint / UsageEvent / UsageCostRecord rows — read-only, "
        "no side effects. See CLAUDE.md's EP-23.3 section for the full architecture."
    ),
)
async def get_provider_connection_sync_status(
    org_id: uuid.UUID,
    connection_id: uuid.UUID,
    db: DbDep,
    _member: Annotated[Membership, RequirePermission(Permission.PROVIDER_READ)],
) -> SyncStatusResponse:
    repo = ProviderConnectionRepository(db)
    conn = await _get_owned_connection(repo, org_id, connection_id)

    sync_service = ProviderSyncService(db)
    sync_status = await sync_service.get_sync_status(organization_id=org_id, connection=conn)
    return _to_sync_status_response(sync_status, conn)


@router.post(
    "/{connection_id}/sync",
    response_model=TriggerSyncResponse,
    summary="Manually trigger a usage synchronization for one provider connection",
    description=(
        "Decrypts the connection's stored credential in memory only, fetches usage "
        "from the provider (incrementally, resuming from the last checkpoint), "
        "normalizes and persists it via the existing UsageCollectionService, and "
        "updates the sync status. Always returns a terminal run (completed or "
        "failed) — a provider-side failure is a normal response, not a 500."
    ),
)
async def sync_provider_connection(
    org_id: uuid.UUID,
    connection_id: uuid.UUID,
    db: DbDep,
    _member: Annotated[Membership, RequirePermission(Permission.PROVIDER_WRITE)],
) -> TriggerSyncResponse:
    repo = ProviderConnectionRepository(db)
    conn = await _get_owned_connection(repo, org_id, connection_id)

    sync_service = ProviderSyncService(db)
    run = await sync_service.sync_connection(organization_id=org_id, connection=conn)
    sync_status = await sync_service.get_sync_status(organization_id=org_id, connection=conn)

    return TriggerSyncResponse(
        run=_to_run_response(run, conn),
        sync_status=_to_sync_status_response(sync_status, conn),
    )


@router.post(
    "/sync",
    response_model=SyncAllResponse,
    summary="Manually trigger a usage synchronization for every active provider connection",
    description=(
        "Runs sync_connection for every active connection in the organization. One "
        "connection's failure never stops the others — every outcome is included "
        "in the response."
    ),
)
async def sync_all_provider_connections(
    org_id: uuid.UUID,
    db: DbDep,
    _member: Annotated[Membership, RequirePermission(Permission.PROVIDER_WRITE)],
) -> SyncAllResponse:
    conn_repo = ProviderConnectionRepository(db)
    sync_service = ProviderSyncService(db)
    runs = await sync_service.sync_all_connections(organization_id=org_id)

    responses: list[SyncRunResponse] = []
    succeeded = 0
    for run in runs:
        conn = (
            await conn_repo.get(run.provider_connection_id) if run.provider_connection_id else None
        )
        if conn is None:
            continue
        responses.append(_to_run_response(run, conn))
        if run.status.value == "completed":
            succeeded += 1

    return SyncAllResponse(
        runs=responses,
        total=len(responses),
        succeeded=succeeded,
        failed=len(responses) - succeeded,
    )


# ── Background scheduler (EP-23.4) ──────────────────────────────────────────


def _to_job_item(record: SchedulerJobRecord) -> SchedulerJobItem:
    return SchedulerJobItem(
        job_id=str(record.job_id),
        organization_id=str(record.organization_id),
        status=record.status.value,
        queued_at=record.queued_at,
        started_at=record.started_at,
        completed_at=record.completed_at,
        connections_synced=record.connections_synced,
        connections_failed=record.connections_failed,
        records_imported=record.records_imported,
        retry_count=record.retry_count,
        duration_seconds=record.duration_seconds,
        error=record.error,
    )


def _scheduler_health(org_status: SchedulerOrgStatus, *, scheduler_is_running: bool) -> str:
    if not org_status.auto_sync_enabled:
        return "disabled"
    if not scheduler_is_running:
        return "not_running"
    if org_status.last_sync_status == "failed":
        return "degraded"
    return "healthy"


def _to_scheduler_status_response(
    org_id: uuid.UUID, org_status: SchedulerOrgStatus, monitoring: dict[str, Any]
) -> SchedulerStatusResponse:
    return SchedulerStatusResponse(
        organization_id=str(org_id),
        auto_sync_enabled=org_status.auto_sync_enabled,
        interval=interval_label_for(org_status.interval_seconds),
        interval_seconds=org_status.interval_seconds,
        last_sync_at=org_status.last_sync_at,
        last_sync_status=org_status.last_sync_status,
        next_sync_at=org_status.next_sync_at,
        current_job=_to_job_item(org_status.current_job) if org_status.current_job else None,
        scheduler_health=_scheduler_health(
            org_status, scheduler_is_running=bool(monitoring["is_running"])
        ),
        monitoring=SchedulerMonitoringSnapshot(**monitoring),
    )


async def _get_org(db: DbDep, org_id: uuid.UUID) -> Organization:
    org = await OrganizationRepository(db).get(org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return org


@router.get(
    "/scheduler/status",
    response_model=SchedulerStatusResponse,
    summary="Get the organization's background sync scheduler status",
    description=(
        "Auto-sync configuration (enabled, interval), last/next sync, and "
        "process-wide scheduler health/monitoring counters — everything the "
        "Connections and Settings pages need in one call. Read-only, no side "
        "effects."
    ),
)
async def get_scheduler_status(
    org_id: uuid.UUID,
    db: DbDep,
    scheduler: SchedulerDep,
    _member: Annotated[Membership, RequirePermission(Permission.PROVIDER_READ)],
) -> SchedulerStatusResponse:
    org = await _get_org(db, org_id)
    org_status = await scheduler.get_org_status(org_id, org.sync_settings)
    monitoring = scheduler.monitoring_snapshot()
    return _to_scheduler_status_response(org_id, org_status, monitoring)


@router.patch(
    "/scheduler/settings",
    response_model=SchedulerStatusResponse,
    summary="Configure the organization's background sync scheduler",
    description=(
        "Enable/disable automatic sync and set its interval (5m/15m/1h/6h/24h). "
        "Stored as a shallow-merged JSON bag on the organization "
        "(organizations.sync_settings, EP-23.4) — the same 'avoid a dedicated "
        "table' pattern EP-22.2 used for users.preferences."
    ),
)
async def update_scheduler_settings(
    org_id: uuid.UUID,
    body: UpdateSchedulerSettingsRequest,
    db: DbDep,
    scheduler: SchedulerDep,
    _member: Annotated[Membership, RequirePermission(Permission.PROVIDER_WRITE)],
) -> SchedulerStatusResponse:
    org = await _get_org(db, org_id)
    org_repo = OrganizationRepository(db)

    patch: dict[str, object] = {}
    if body.auto_sync_enabled is not None:
        patch["auto_sync_enabled"] = body.auto_sync_enabled
    if body.interval is not None:
        patch["interval_seconds"] = INTERVAL_PRESETS[body.interval]

    if patch:
        merged = {**org.sync_settings, **patch}
        org = await org_repo.update(org, sync_settings=merged)

    org_status = await scheduler.get_org_status(org_id, org.sync_settings)
    monitoring = scheduler.monitoring_snapshot()
    return _to_scheduler_status_response(org_id, org_status, monitoring)


@router.get(
    "/scheduler/jobs",
    response_model=SchedulerJobsResponse,
    summary="Recent background sync jobs for this organization",
    description=(
        "In-memory job history for this scheduler process (queued/running/"
        "completed/failed, duration, records imported, retry count) — see "
        "CLAUDE.md's EP-23.4 section for why this is process-scoped rather "
        "than a persisted table."
    ),
)
async def list_scheduler_jobs(
    org_id: uuid.UUID,
    db: DbDep,
    scheduler: SchedulerDep,
    _member: Annotated[Membership, RequirePermission(Permission.PROVIDER_READ)],
    limit: int = 20,
) -> SchedulerJobsResponse:
    await _get_org(db, org_id)
    jobs = scheduler.jobs_for(org_id, limit=limit)
    items = [_to_job_item(j) for j in jobs]
    return SchedulerJobsResponse(jobs=items, total=len(items))
