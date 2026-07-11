"""Projects API — EP-23.

Endpoints:
  GET    /v1/organizations/{org_id}/projects              — list projects
  POST   /v1/organizations/{org_id}/projects              — create a project
  PATCH  /v1/organizations/{org_id}/projects/{project_id} — rename/update a project
  DELETE /v1/organizations/{org_id}/projects/{project_id} — soft-delete a project

Authorization: PROJECT_READ for list, PROJECT_WRITE for create/update,
PROJECT_DELETE for delete — all already defined in app.auth.rbac (EP-13),
granted to every role down to VIEWER for read and MEMBER+ for write/delete.

The Project model and ProjectRepository (app.models.project,
app.repositories.project_repository) already existed — this EP adds only
the API layer on top of them, following the same pattern as
app.api.v1.organizations. No migration required.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, status

from app.api.deps import DbDep
from app.auth.dependencies import RequirePermission
from app.auth.rbac import Permission
from app.db.mixins import uuid7
from app.models.membership import Membership
from app.models.project import Project, ProjectEnvironment
from app.repositories.project_repository import ProjectRepository
from app.schemas.projects import (
    CreateProjectRequest,
    ProjectResponse,
    ProjectsListResponse,
    UpdateProjectRequest,
)

router = APIRouter(prefix="/organizations/{org_id}/projects", tags=["projects"])


def _parse_environment(value: str) -> ProjectEnvironment:
    try:
        return ProjectEnvironment(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"Invalid environment {value!r}. "
                f"Must be one of: {[e.value for e in ProjectEnvironment]}"
            ),
        ) from exc


def _to_response(project: Project) -> ProjectResponse:
    return ProjectResponse(
        id=project.id,  # EP-26.0.3.1 — raw UUID, matches the {project_id} path param type
        name=project.name,
        description=project.description,
        environment=project.environment.value,
        budget=project.budget,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@router.get(
    "",
    response_model=ProjectsListResponse,
    summary="List projects in an organization",
)
async def list_projects(
    org_id: uuid.UUID,
    db: DbDep,
    _member: Annotated[Membership, RequirePermission(Permission.PROJECT_READ)],
) -> ProjectsListResponse:
    repo = ProjectRepository(db)
    page = await repo.list_by_org(org_id, limit=100)
    return ProjectsListResponse(
        projects=[_to_response(p) for p in page.items],
        total=len(page.items),
    )


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a project",
)
async def create_project(
    org_id: uuid.UUID,
    body: CreateProjectRequest,
    db: DbDep,
    _member: Annotated[Membership, RequirePermission(Permission.PROJECT_WRITE)],
) -> ProjectResponse:
    project = Project()
    project.id = uuid7()
    project.organization_id = org_id
    project.name = body.name
    project.description = body.description
    project.environment = _parse_environment(body.environment)
    project.budget = body.budget

    repo = ProjectRepository(db)
    created = await repo.create(project)
    return _to_response(created)


@router.patch(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Rename or update a project",
)
async def update_project(
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    body: UpdateProjectRequest,
    db: DbDep,
    _member: Annotated[Membership, RequirePermission(Permission.PROJECT_WRITE)],
) -> ProjectResponse:
    repo = ProjectRepository(db)
    project = await repo.get(project_id)
    if project is None or project.organization_id != org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    updates = body.model_dump(exclude_unset=True)
    if "environment" in updates:
        updates["environment"] = _parse_environment(updates["environment"])

    updated = await repo.update(project, **updates) if updates else project
    return _to_response(updated)


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a project",
)
async def delete_project(
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    db: DbDep,
    _member: Annotated[Membership, RequirePermission(Permission.PROJECT_DELETE)],
) -> None:
    repo = ProjectRepository(db)
    project = await repo.get(project_id)
    if project is None or project.organization_id != org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    await repo.soft_delete(project)
