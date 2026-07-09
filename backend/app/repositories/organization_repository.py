"""
OrganizationRepository — data access for Organization entities.

Only data-access logic belongs here. Business rules (e.g., "an ARCHIVED
organization cannot be reactivated") belong in the service layer (EP-04+).
"""

from __future__ import annotations

import uuid

from sqlalchemy import and_, exists, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

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
        """
        Return True if the slug is already taken by another active Organization.

        Uses SELECT EXISTS(SELECT 1 ...) instead of fetching the full ORM row,
        which avoids unnecessary column hydration and is faster at scale.
        """
        inner = (
            select(literal(1))
            .select_from(Organization)
            .where(
                Organization.deleted_at.is_(None),
                Organization.slug == slug,
            )
        )
        if exclude_id is not None:
            inner = inner.where(Organization.id != exclude_id)
        stmt = select(exists(inner))
        result = await self._session.execute(stmt)
        return bool(result.scalar_one())

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

    async def list_auto_sync_enabled(
        self, *, limit: int = 100, cursor: str | None = None
    ) -> CursorPage[Organization]:
        """Active organizations with the background sync scheduler turned on (EP-23.4).

        Reads ``sync_settings->>'auto_sync_enabled'`` directly rather than
        loading every organization and filtering in Python — a missing key
        (the default for every pre-existing org) is correctly excluded,
        since ``.astext`` on an absent JSONB key is SQL NULL, not ``"true"``.
        Cursor-paginated like every other listing in this repository
        (``list_page`` caps ``limit`` at 100) — the scheduler tick walks
        every page via ``next_cursor`` rather than assuming one page covers
        every organization.
        """
        return await self.list_page(
            limit=limit,
            cursor=cursor,
            order="asc",
            extra_filters=and_(
                Organization.status == OrganizationStatus.ACTIVE,
                Organization.sync_settings["auto_sync_enabled"].astext == "true",
            ),
        )
