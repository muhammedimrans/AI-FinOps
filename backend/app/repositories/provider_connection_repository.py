"""
ProviderConnectionRepository — data access for ProviderConnection entities.

ProviderConnections are always scoped to an Organization (DP-6) and
optionally to a Project. The repository enforces org-scoped isolation
on every multi-record query.
"""

from __future__ import annotations

import uuid

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.provider_connection import ProviderConnection, ProviderType
from app.repositories.base_repository import BaseRepository, CursorPage


class ProviderConnectionRepository(BaseRepository[ProviderConnection]):
    """Repository for ProviderConnection CRUD and queries."""

    model = ProviderConnection

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def list_by_org(
        self,
        org_id: uuid.UUID,
        *,
        limit: int = 20,
        cursor: str | None = None,
        order: str = "asc",
    ) -> CursorPage[ProviderConnection]:
        """Return all active ProviderConnections for the given Organization."""
        return await self.list_page(
            limit=limit,
            cursor=cursor,
            order=order,
            extra_filters=ProviderConnection.organization_id == org_id,
        )

    async def list_active_by_org(
        self,
        org_id: uuid.UUID,
        *,
        limit: int = 20,
        cursor: str | None = None,
        order: str = "asc",
    ) -> CursorPage[ProviderConnection]:
        """Return only is_active=True connections for the given Organization."""
        return await self.list_page(
            limit=limit,
            cursor=cursor,
            order=order,
            extra_filters=and_(
                ProviderConnection.organization_id == org_id,
                ProviderConnection.is_active.is_(True),
            ),
        )

    async def list_by_project(
        self,
        project_id: uuid.UUID,
        *,
        limit: int = 20,
        cursor: str | None = None,
        order: str = "asc",
    ) -> CursorPage[ProviderConnection]:
        """Return all active ProviderConnections scoped to the given Project."""
        return await self.list_page(
            limit=limit,
            cursor=cursor,
            order=order,
            extra_filters=ProviderConnection.project_id == project_id,
        )

    async def list_by_type(
        self,
        org_id: uuid.UUID,
        provider_type: ProviderType,
        *,
        limit: int = 20,
        cursor: str | None = None,
    ) -> CursorPage[ProviderConnection]:
        """Return connections of a specific provider type within an Organization."""
        return await self.list_page(
            limit=limit,
            cursor=cursor,
            extra_filters=and_(
                ProviderConnection.organization_id == org_id,
                ProviderConnection.provider_type == provider_type,
            ),
        )

    async def list_recent_failures(
        self,
        org_id: uuid.UUID,
        *,
        limit: int = 10,
    ) -> list[ProviderConnection]:
        """Connections with a recorded failure, most recent first (EP-24.1).

        Powers the "Provider failures" section of the Recent Activity feed.
        Reuses the ``last_failure_at``/``health_status`` fields EP-19.3/EP-22
        already maintain — no new column, no separate failure log table.
        """
        stmt = (
            select(ProviderConnection)
            .where(
                and_(
                    ProviderConnection.organization_id == org_id,
                    ProviderConnection.deleted_at.is_(None),
                    ProviderConnection.last_failure_at.is_not(None),
                )
            )
            .order_by(ProviderConnection.last_failure_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
