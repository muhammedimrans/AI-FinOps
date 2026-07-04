"""UsageCollectionCheckpointRepository — F-044 / F-045 (EP-08).

One checkpoint per (organization_id, provider, provider_connection_id) triple.
``upsert()`` creates or updates the checkpoint atomically so that concurrent
collection tasks do not race.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import and_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.mixins import uuid7
from app.models.usage_collection_checkpoint import UsageCollectionCheckpoint
from app.repositories.base_repository import BaseRepository, CursorPage


class UsageCollectionCheckpointRepository(BaseRepository[UsageCollectionCheckpoint]):
    """Repository for UsageCollectionCheckpoint with upsert support."""

    model = UsageCollectionCheckpoint

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_by_org_provider(
        self,
        organization_id: uuid.UUID,
        provider: str,
        provider_connection_id: uuid.UUID | None = None,
    ) -> UsageCollectionCheckpoint | None:
        filters = [
            UsageCollectionCheckpoint.organization_id == organization_id,
            UsageCollectionCheckpoint.provider == provider,
        ]
        if provider_connection_id is not None:
            filters.append(
                UsageCollectionCheckpoint.provider_connection_id == provider_connection_id
            )
        else:
            filters.append(UsageCollectionCheckpoint.provider_connection_id.is_(None))

        stmt = self._active_query().where(and_(*filters))
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert(
        self,
        *,
        organization_id: uuid.UUID,
        provider: str,
        provider_connection_id: uuid.UUID | None = None,
        last_collected_at: datetime,
        cursor: str | None = None,
        page_token: str | None = None,
        sync_state: dict[str, Any] | None = None,
        last_run_id: uuid.UUID | None = None,
    ) -> UsageCollectionCheckpoint:
        """Insert or update the checkpoint for this (org, provider, connection) triple."""
        stmt = (
            pg_insert(UsageCollectionCheckpoint)
            .values(
                id=uuid7(),
                organization_id=organization_id,
                provider=provider,
                provider_connection_id=provider_connection_id,
                last_collected_at=last_collected_at,
                cursor=cursor,
                page_token=page_token,
                sync_state=sync_state or {},
                last_run_id=last_run_id,
            )
            .on_conflict_do_update(
                constraint="uq_usage_checkpoints_org_provider_connection",
                set_={
                    "last_collected_at": last_collected_at,
                    "cursor": cursor,
                    "page_token": page_token,
                    "sync_state": sync_state or {},
                    "last_run_id": last_run_id,
                },
            )
            .returning(UsageCollectionCheckpoint.id)
        )
        result = await self._session.execute(stmt)
        row = result.fetchone()
        checkpoint_id = row[0] if row else None

        if checkpoint_id:
            updated = await self.get(checkpoint_id)
            if updated:
                return updated

        obj = UsageCollectionCheckpoint()
        obj.organization_id = organization_id
        obj.provider = provider
        obj.provider_connection_id = provider_connection_id
        obj.last_collected_at = last_collected_at
        obj.cursor = cursor
        obj.page_token = page_token
        obj.sync_state = sync_state or {}
        obj.last_run_id = last_run_id
        return await self.create(obj)

    async def list_by_org(
        self,
        organization_id: uuid.UUID,
        *,
        limit: int = 20,
        cursor: str | None = None,
    ) -> CursorPage[UsageCollectionCheckpoint]:
        return await self.list_page(
            limit=limit,
            cursor=cursor,
            order="asc",
            extra_filters=UsageCollectionCheckpoint.organization_id == organization_id,
        )
