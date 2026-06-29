"""
OrganizationRepository — data access for Organization entities.

Only data-access logic belongs here. Business rules (e.g., "an ARCHIVED
organization cannot be reactivated") belong in the service layer (EP-04+).
"""
from __future__ import annotations

import uuid

from sqlalchemy import and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.mixins import BaseModel
from app.models.organization import Organization, OrganizationStatus
from app.repositories.base_repository import BaseRepository, CursorPage


class OrganizationRepository(BaseRepository[Organization]):
    """Repository for Organization CRUD and queries."""

    model = Organization

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_by_slug(self, slug: str) -> Organization | None:
        """Return the active Organization with the given slug, or None."""
        stmt = self._active_query().where(Organization.slug == slug)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def slug_exists(self, slug: str, *, exclude_id: uuid.UUID | None = None) -> bool:
        """Return True if the slug is already taken by another active Organization."""
        stmt = self._active_query().where(Organization.slug == slug)
        if exclude_id is not None:
            stmt = stmt.where(Organization.id != exclude_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def list_by_status(
        self,
        status: OrganizationStatus,
        *,
        limit: int = 20,
        cursor: str | None = None,
        order: str = "asc",
    ) -> CursorPage[Organization]:
        """Return a cursor-paginated page of organizations filtered by status."""
        return await self.list_page(
            limit=limit,
            cursor=cursor,
            order=order,
            extra_filters=Organization.status == status,
        )
