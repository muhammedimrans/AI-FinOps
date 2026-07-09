"""Request/response schemas for /v1/organizations/{org_id}/api-keys (EP-14 Phase 1)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ExpirationOption = Literal["never", "30d", "90d"]


class CreateApiKeyRequest(BaseModel):
    """Create a new organization API key."""

    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    permissions: list[str] = Field(default_factory=list)
    expiration: ExpirationOption = "never"


class UpdateApiKeyRequest(BaseModel):
    """Rename/redescribe an existing API key (EP-22.2 Settings — API Keys section).

    Only ``name``/``description`` are editable — permissions, expiration,
    and the key material itself are immutable after creation (rotating
    scope or expiry means issuing a new key).
    """

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class ApiKeyResponse(BaseModel):
    """One API key, safe to return from GET/LIST — never the raw key or its hash."""

    id: uuid.UUID
    name: str
    description: str | None
    prefix: str
    permissions: list[str]
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None


class ApiKeysListResponse(BaseModel):
    """All API keys for an organization."""

    keys: list[ApiKeyResponse]
    total: int


class ApiKeyCreatedResponse(BaseModel):
    """
    Response to a successful key creation.

    api_key is the full raw secret — it is returned here and only here. It
    cannot be retrieved again; the caller must store it now.
    """

    id: uuid.UUID
    api_key: str
    prefix: str
    name: str
    permissions: list[str]
    created_at: datetime
    expires_at: datetime | None
