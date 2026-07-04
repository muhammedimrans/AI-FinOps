"""UsageCollectionRunRepository — F-045 (EP-08)."""

from __future__ import annotations

import uuid

from sqlalchemy import and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.usage_collection_run import CollectionRunStatus, UsageCollectionRun
from app.repositories.base_repository import BaseRepository, CursorPage


class UsageCollectionRunRepository(BaseRepository[UsageCollectionRun]):
    """Repository for UsageCollectionRun lifecycle management."""

    model = UsageCollectionRun

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def list_by_org(
        self,
        organization_id: uuid.UUID,
        *,
        limit: int = 20,
        cursor: str | None = None,
        order: str = "desc",
    ) -> CursorPage[UsageCollectionRun]:
        return await self.list_page(
            limit=limit,
            cursor=cursor,
            order=order,
            extra_filters=UsageCollectionRun.organization_id == organization_id,
        )

    async def list_by_provider(
        self,
        organization_id: uuid.UUID,
        provider: str,
        *,
        limit: int = 20,
        cursor: str | None = None,
        order: str = "desc",
    ) -> CursorPage[UsageCollectionRun]:
        return await self.list_page(
            limit=limit,
            cursor=cursor,
            order=order,
            extra_filters=and_(
                UsageCollectionRun.organization_id == organization_id,
                UsageCollectionRun.provider == provider,
            ),
        )

    async def list_by_status(
        self,
        organization_id: uuid.UUID,
        status: CollectionRunStatus,
        *,
        limit: int = 20,
        cursor: str | None = None,
    ) -> CursorPage[UsageCollectionRun]:
        return await self.list_page(
            limit=limit,
            cursor=cursor,
            order="desc",
            extra_filters=and_(
                UsageCollectionRun.organization_id == organization_id,
                UsageCollectionRun.status == status,
            ),
        )

    async def get_latest_for_provider(
        self,
        organization_id: uuid.UUID,
        provider: str,
    ) -> UsageCollectionRun | None:
        page = await self.list_by_provider(organization_id, provider, limit=1, order="desc")
        return page.items[0] if page.items else None
