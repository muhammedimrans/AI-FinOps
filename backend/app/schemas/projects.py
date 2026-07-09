"""Request/response schemas for the /v1/organizations/{org_id}/projects endpoints (EP-23)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class ProjectResponse(BaseModel):
    """One Project."""

    id: str  # external_id (proj_...)
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
