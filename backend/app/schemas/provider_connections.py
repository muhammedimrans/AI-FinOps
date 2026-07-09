"""Request/response schemas for /v1/organizations/{org_id}/provider-connections (EP-22)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ProviderConnectionResponse(BaseModel):
    """One configured provider connection."""

    id: str  # external_id (conn_...)
    provider_type: str  # ProviderType value
    display_name: str
    project_id: str | None  # raw UUID string, None = org-scoped (not project-scoped)
    is_active: bool
    health_status: str  # ProviderHealthStatus value
    last_failure_at: datetime | None
    last_recovery_at: datetime | None
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

    No API key/secret field here by design — ProviderConnection stores
    non-secret metadata only (see the model's own docstring); this repo has
    no secrets vault yet to hold credentials safely. "Test connection"
    (POST .../test) checks connectivity using the server-side environment
    variable credentials the existing GET /v1/providers/{provider}/test
    endpoint already relies on, not a per-connection user-supplied key.
    """

    provider_type: str  # ProviderType value
    display_name: str = Field(min_length=1, max_length=255)
    # Raw UUID, not external_id — matches every other org-scoped body/path
    # reference in this API (org_id, membership_id, key_id, ...).
    project_id: uuid.UUID | None = None


class UpdateProviderConnectionRequest(BaseModel):
    """Update a provider connection. All fields optional — only supplied fields change."""

    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    project_id: uuid.UUID | None = None
    is_active: bool | None = None


class TestProviderConnectionResponse(BaseModel):
    """Result of testing a specific connection's underlying provider."""

    connection_id: str
    provider_type: str
    health_status: str  # ProviderHealthStatus value
    tested: bool  # False when the provider has no production-ready adapter yet
    detail: str
