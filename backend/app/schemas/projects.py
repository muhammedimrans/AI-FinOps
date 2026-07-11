"""Request/response schemas for the /v1/organizations/{org_id}/projects endpoints (EP-23)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class ProjectResponse(BaseModel):
    """One Project.

    ``id`` is the raw UUID (EP-26.0.3.1 fix), not ``external_id`` — every
    mutating endpoint on this resource (``PATCH``/``DELETE .../{project_id}``)
    type-validates its path parameter as ``uuid.UUID``, and
    ``uuid.UUID("proj_<hex>")`` always raises (the "proj_" prefix isn't valid
    hex). Returning ``external_id`` here meant every client that reused this
    response's own ``id`` to build a follow-up request — exactly what the
    frontend does — would 422 on every rename/delete. Matches the existing,
    already-correct convention `BudgetResponse`/`AlertResponse`/
    `ApiKeyResponse`/`InvitationResponse` all use.
    """

    id: uuid.UUID
    name: str
    description: str | None
    environment: str  # ProjectEnvironment value
    budget: Decimal | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectsListResponse(BaseModel):
    """All projects in an organization."""

    projects: list[ProjectResponse]
    total: int


class CreateProjectRequest(BaseModel):
    """Create a new Project."""

    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    environment: str = "production"  # ProjectEnvironment value
    budget: Decimal | None = Field(default=None, ge=0)


class UpdateProjectRequest(BaseModel):
    """Rename/update a Project. All fields optional — only supplied fields change."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    environment: str | None = None  # ProjectEnvironment value
    budget: Decimal | None = Field(default=None, ge=0)
