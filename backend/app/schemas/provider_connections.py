"""Request/response schemas for /v1/organizations/{org_id}/provider-connections (EP-22)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ProviderConnectionResponse(BaseModel):
    """One configured provider connection.

    Never carries the decrypted API key — ``masked_api_key`` is the only
    credential-derived field, e.g. ``"sk-********************************AbC"``,
    and is None when no credential has been configured yet. See
    ``app.security.masking.mask_secret`` and CLAUDE.md §13's security section.

    ``id`` is the raw UUID (EP-26.0.3.1 fix), not ``external_id`` — every
    mutating endpoint on this resource (``PATCH``/``DELETE``/``test``/
    ``rotate``/``sync-status``/``sync`` under ``.../{connection_id}``)
    type-validates its path parameter as ``uuid.UUID``, and
    ``uuid.UUID("conn_<hex>")`` always raises. The dashboard's Connections
    page reuses this response's own ``id`` for every one of those actions
    (rename, activate/deactivate, Test Connection, Rotate Key, Sync Now,
    Delete) — with the previous ``external_id`` value, every one of them
    would 422 in real use. Matches the same fix applied to
    ``ProjectResponse.id`` in this EP, and the already-correct convention
    ``BudgetResponse``/``AlertResponse``/``ApiKeyResponse`` already use.
    """

    id: uuid.UUID
    provider_type: str  # ProviderType value
    display_name: str
    project_id: str | None  # raw UUID string, None = org-scoped (not project-scoped)
    is_active: bool
    has_credential: bool
    masked_api_key: str | None  # e.g. "sk-********************************AbC"
    base_url: str | None
    health_status: str  # ProviderHealthStatus value — coarse, alert-engine-facing
    last_validation_status: str | None  # ProviderValidationStatus value — fine-grained
    last_error: str | None  # normalized, user-safe message only
    last_failure_at: datetime | None  # "Last Failed Validation"
    last_recovery_at: datetime | None  # "Last Successful Validation"
    consecutive_failure_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProviderConnectionsListResponse(BaseModel):
    """All provider connections in an organization."""

    connections: list[ProviderConnectionResponse]
    total: int


class CreateProviderConnectionRequest(BaseModel):
    """Register a new provider connection.

    ``api_key``, when supplied, is encrypted immediately
    (``ProviderCredentialService.encrypt``) before the connection is ever
    persisted — the plaintext never reaches the database. Optional because
    some providers (Ollama) don't require one, and a connection may
    legitimately be created without a credential and have one added later
    via the rotate endpoint. Supplying a credential triggers an immediate
    live validation (EP-22 Part 3) whose result is reflected in the response.
    """

    provider_type: str  # ProviderType value
    display_name: str = Field(min_length=1, max_length=255)
    api_key: str | None = Field(default=None, min_length=1, max_length=4096)
    base_url: str | None = Field(default=None, max_length=2048)
    # Raw UUID, not external_id — matches every other org-scoped body/path
    # reference in this API (org_id, membership_id, key_id, ...).
    project_id: uuid.UUID | None = None


class UpdateProviderConnectionRequest(BaseModel):
    """Update a provider connection. All fields optional — only supplied fields change.

    Does not accept ``api_key`` — credential rotation is a distinct,
    separately-audited action (``POST .../{id}/rotate``), not a side effect
    of an ordinary metadata edit.
    """

    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    base_url: str | None = Field(default=None, max_length=2048)
    project_id: uuid.UUID | None = None
    is_active: bool | None = None


class RotateProviderConnectionKeyRequest(BaseModel):
    """Replace a connection's API key. Triggers immediate re-validation."""

    api_key: str = Field(min_length=1, max_length=4096)


class TestProviderConnectionResponse(BaseModel):
    """Result of testing a specific connection's underlying provider."""

    connection_id: str
    provider_type: str
    health_status: str  # ProviderHealthStatus value
    last_validation_status: str  # ProviderValidationStatus value
    tested: bool  # False only when no credential is configured for a provider that needs one
    detail: str  # normalized, user-safe message only


class CostImportedItem(BaseModel):
    """One currency's all-time imported cost total for a connection (EP-23.3)."""

    currency: str
    total_cost: str  # Decimal serialized as string — avoids float precision loss
    record_count: int


class SyncStatusResponse(BaseModel):
    """Derived synchronization state for one provider connection (EP-23.3).

    Every field is computed from existing ``UsageCollectionRun`` /
    ``UsageCollectionCheckpoint`` / ``UsageEvent`` / ``UsageCostRecord`` rows
    — see ``app.services.provider_sync_service.ProviderSyncService.
    get_sync_status``. No credential material appears anywhere in this
    response.
    """

    connection_id: str  # external_id
    provider_type: str
    sync_status: str  # "never_synced" | "pending" | "running" | "success" | "failed"
    last_sync_started_at: datetime | None
    last_sync_completed_at: datetime | None
    last_successful_sync_at: datetime | None
    last_error: str | None
    last_imported_at: datetime | None
    records_imported: int
    tokens_imported: int
    estimated_cost_imported: list[CostImportedItem]
    supports_usage_sync: bool


class SyncRunResponse(BaseModel):
    """One completed or failed synchronization run (EP-23.3)."""

    run_id: str  # external_id (run_...)
    connection_id: str  # external_id (conn_...)
    provider_type: str
    status: str  # CollectionRunStatus value: pending/running/completed/failed/cancelled
    started_at: datetime
    completed_at: datetime | None
    records_imported: int
    records_failed: int
    error_message: str | None


class TriggerSyncResponse(BaseModel):
    """Result of manually triggering a sync for one connection."""

    run: SyncRunResponse
    sync_status: SyncStatusResponse


class SyncAllResponse(BaseModel):
    """Result of manually triggering a sync for every active connection in an org."""

    runs: list[SyncRunResponse]
    total: int
    succeeded: int
    failed: int


# ── Background scheduler (EP-23.4) ──────────────────────────────────────────


class UpdateSchedulerSettingsRequest(BaseModel):
    """Configure the organization's background sync scheduler.

    Both fields optional — only supplied fields change, matching every other
    partial-update request in this codebase (``exclude_unset``).
    ``interval`` is one of the 5 presets the product spec names; the
    scheduler stores/derives whole seconds internally
    (``app.services.usage_sync_scheduler.INTERVAL_PRESETS``) but the API
    only ever accepts the label, never a raw second count, so an invalid
    interval can't be persisted.
    """

    auto_sync_enabled: bool | None = None
    interval: Literal["5m", "15m", "1h", "6h", "24h"] | None = None


class SchedulerJobItem(BaseModel):
    """One scheduler-dispatched sync job (queued/running/completed/failed)."""

    job_id: str
    organization_id: str
    status: str  # SchedulerJobStatus value
    queued_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    connections_synced: int
    connections_failed: int
    records_imported: int
    retry_count: int
    duration_seconds: float | None
    error: str | None


class SchedulerMonitoringSnapshot(BaseModel):
    """Process-wide scheduler counters — see ``UsageSyncScheduler.monitoring_snapshot``."""

    is_running: bool
    active_jobs: int
    queued_jobs: int
    completed_jobs: int
    failed_jobs: int
    average_duration_seconds: float | None
    last_execution: datetime | None


class SchedulerStatusResponse(BaseModel):
    """Auto-sync configuration + state for one organization, plus
    process-wide scheduler health — everything the Connections and Settings
    pages need in a single call."""

    organization_id: str
    auto_sync_enabled: bool
    interval: str  # "5m" | "15m" | "1h" | "6h" | "24h"
    interval_seconds: int
    last_sync_at: datetime | None
    last_sync_status: str | None  # CollectionRunStatus value, or None if never synced
    next_sync_at: datetime | None
    current_job: SchedulerJobItem | None
    scheduler_health: str  # "healthy" | "degraded" | "disabled" | "not_running"
    monitoring: SchedulerMonitoringSnapshot


class SchedulerJobsResponse(BaseModel):
    """Recent scheduler job history for one organization."""

    jobs: list[SchedulerJobItem]
    total: int
