"""Usage collection API request/response schemas — EP-08."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ValidationInfo, field_validator

from app.models.usage_collection_run import CollectionRunStatus, CollectionTrigger

# ── Request schemas ────────────────────────────────────────────────────────────


class CollectUsageRequest(BaseModel):
    """Body for POST /usage/collect and POST /usage/collect/{provider}."""

    organization_id: uuid.UUID
    start_date: datetime
    end_date: datetime
    provider_connection_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    triggered_by: CollectionTrigger = CollectionTrigger.MANUAL

    @field_validator("end_date")
    @classmethod
    def _end_after_start(cls, v: datetime, info: ValidationInfo) -> datetime:
        start = info.data.get("start_date")
        if start and v <= start:
            raise ValueError("end_date must be after start_date")
        return v


# ── Response schemas ───────────────────────────────────────────────────────────


class UsageEventResponse(BaseModel):
    """Serialized UsageEvent for API responses."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    external_id: str
    organization_id: uuid.UUID
    project_id: uuid.UUID | None
    provider_connection_id: uuid.UUID | None
    collection_run_id: uuid.UUID | None
    provider: str
    provider_request_id: str
    model: str
    timestamp: datetime
    request_count: int
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int | None
    total_tokens: int
    event_metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class UsageEventListResponse(BaseModel):
    """Paginated list of usage events."""

    model_config = {"frozen": True}

    items: list[UsageEventResponse]
    next_cursor: str | None
    has_more: bool
    count: int


class CollectionRunResponse(BaseModel):
    """Serialized UsageCollectionRun for API responses."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    external_id: str
    organization_id: uuid.UUID
    provider_connection_id: uuid.UUID | None
    provider: str
    status: CollectionRunStatus
    triggered_by: CollectionTrigger
    started_at: datetime
    completed_at: datetime | None
    collection_start: datetime
    collection_end: datetime
    events_collected: int
    events_failed: int
    pages_fetched: int
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class CollectionRunListResponse(BaseModel):
    """Paginated list of collection runs."""

    model_config = {"frozen": True}

    items: list[CollectionRunResponse]
    next_cursor: str | None
    has_more: bool
    count: int


class CheckpointResponse(BaseModel):
    """Serialized UsageCollectionCheckpoint for API responses."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    external_id: str
    organization_id: uuid.UUID
    provider_connection_id: uuid.UUID | None
    provider: str
    last_collected_at: datetime
    cursor: str | None
    page_token: str | None
    sync_state: dict[str, Any]
    last_run_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class CheckpointListResponse(BaseModel):
    """Paginated list of checkpoints."""

    model_config = {"frozen": True}

    items: list[CheckpointResponse]
    next_cursor: str | None
    has_more: bool
    count: int


class ProviderCollectionStatusResponse(BaseModel):
    """Provider collection status for GET /usage/providers/{provider}/status."""

    model_config = {"frozen": True}

    provider: str
    organization_id: uuid.UUID
    last_collected_at: datetime | None
    last_run_status: CollectionRunStatus | None
    last_run_id: uuid.UUID | None
    events_total: int
    has_checkpoint: bool
