"""
ProjectRepository — data access for Project entities.

Projects are always scoped to an Organization (DP-6); every query method
accepts an org_id to enforce tenant isolation at the repository level.
"""

from __future__ import annotations

import uuid

from sqlalchemy import and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project, ProjectEnvironment
from app.repositories.base_repository import BaseRepository, CursorPage


class ProjectRepository(BaseRepository[Project]):
    """Repository for Project CRUD and queries."""

    model = Project

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def list_by_org(
        self,
        org_id: uuid.UUID,
        *,
        limit: int = 20,
        cursor: str | None = None,
        order: str = "asc",
    ) -> CursorPage[Project]:
        """Return all active Projects for the given Organization."""
        return await self.list_page(
            limit=limit,
            cursor=cursor,
            order=order,
            extra_filters=Project.organization_id == org_id,
        )

    async def list_by_org_and_env(
        self,
        org_id: uuid.UUID,
        environment: ProjectEnvironment,
        *,
        limit: int = 20,
        cursor: str | None = None,
        order: str = "asc",
    ) -> CursorPage[Project]:
        """Return active Projects for a specific org + environment combination."""
        return await self.list_page(
            limit=limit,
            cursor=cursor,
            order=order,
            extra_filters=and_(
                Project.organization_id == org_id,
                Project.environment == environment,
            ),
        )

    async def count_by_org(self, org_id: uuid.UUID) -> int:
        """Return the count of active Projects for the given Organization."""
        return await self.count(extra_filters=Project.organization_id == org_id)
