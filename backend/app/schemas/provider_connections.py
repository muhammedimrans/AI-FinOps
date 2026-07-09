"""Request/response schemas for /v1/organizations/{org_id}/provider-connections (EP-22)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ProviderConnectionResponse(BaseModel):
    """One configured provider connection.

    Never carries the decrypted API key — ``masked_api_key`` is the only
    credential-derived field, e.g. ``"sk-********************************AbC"``,
    and is None when no credential has been configured yet. See
    ``app.security.masking.mask_secret`` and CLAUDE.md §13's security section.
    """

    id: str  # external_id (conn_...)
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
