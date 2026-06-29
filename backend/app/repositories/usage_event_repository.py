"""UsageEventRepository — F-045 (EP-08).

Provides CRUD, idempotent upsert, and multi-dimensional filtering for
``UsageEvent`` records.

Idempotent upsert
-----------------
``upsert()`` uses PostgreSQL ``INSERT … ON CONFLICT (organization_id, provider,
provider_request_id) DO UPDATE`` so re-collecting the same event updates the
existing row rather than raising a duplicate-key error.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import and_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.mixins import uuid7
from app.models.usage_event import UsageEvent
from app.repositories.base_repository import BaseRepository, CursorPage


class UsageEventRepository(BaseRepository[UsageEvent]):
    """Repository for UsageEvent CRUD, upsert, and filtered queries."""

    model = UsageEvent

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    # ── Idempotent upsert ─────────────────────────────────────────────────────

    async def upsert(self, event: UsageEvent) -> UsageEvent:
        """Insert or update a usage event using the dedup constraint.

        If a row with the same ``(organization_id, provider, provider_request_id)``
        already exists, its mutable columns are updated in-place and the existing
        ``id`` is preserved.
        """
        tbl = UsageEvent.__table__
        stmt = (
            pg_insert(tbl)
            .values(
                id=event.id if event.id else uuid7(),
                organization_id=event.organization_id,
                project_id=event.project_id,
                provider_connection_id=event.provider_connection_id,
                collection_run_id=event.collection_run_id,
                provider=event.provider,
                provider_request_id=event.provider_request_id,
                model=event.model,
                timestamp=event.timestamp,
                request_count=event.request_count,
                prompt_tokens=event.prompt_tokens,
                completion_tokens=event.completion_tokens,
                cached_tokens=event.cached_tokens,
                total_tokens=event.total_tokens,
                metadata=event.event_metadata,
                raw_provider_payload=event.raw_provider_payload,
            )
            .on_conflict_do_update(
                constraint="uq_usage_events_dedup",
                set_={
                    "model": event.model,
                    "timestamp": event.timestamp,
                    "request_count": event.request_count,
                    "prompt_tokens": event.prompt_tokens,
                    "completion_tokens": event.completion_tokens,
                    "cached_tokens": event.cached_tokens,
                    "total_tokens": event.total_tokens,
                    "metadata": event.event_metadata,
                    "raw_provider_payload": event.raw_provider_payload,
                    "collection_run_id": event.collection_run_id,
                },
            )
            .returning(tbl.c.id)
        )
        result = await self._session.execute(stmt)
        row = result.fetchone()
        if row:
            event.id = row[0]
        return event

    # ── Lookup by dedup key ───────────────────────────────────────────────────

    async def get_by_provider_request_id(
        self,
        organization_id: uuid.UUID,
        provider: str,
        provider_request_id: str,
    ) -> UsageEvent | None:
        stmt = self._active_query().where(
            and_(
                UsageEvent.organization_id == organization_id,
                UsageEvent.provider == provider,
                UsageEvent.provider_request_id == provider_request_id,
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    # ── Filtered list queries ─────────────────────────────────────────────────

    async def list_by_org(
        self,
        organization_id: uuid.UUID,
        *,
        limit: int = 20,
        cursor: str | None = None,
        order: str = "desc",
    ) -> CursorPage[UsageEvent]:
        return await self.list_page(
            limit=limit,
            cursor=cursor,
            order=order,
            extra_filters=UsageEvent.organization_id == organization_id,
        )

    async def list_by_provider(
        self,
        organization_id: uuid.UUID,
        provider: str,
        *,
        limit: int = 20,
        cursor: str | None = None,
        order: str = "desc",
    ) -> CursorPage[UsageEvent]:
        return await self.list_page(
            limit=limit,
            cursor=cursor,
            order=order,
            extra_filters=and_(
                UsageEvent.organization_id == organization_id,
                UsageEvent.provider == provider,
            ),
        )

    async def list_by_project(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        *,
        limit: int = 20,
        cursor: str | None = None,
        order: str = "desc",
    ) -> CursorPage[UsageEvent]:
        return await self.list_page(
            limit=limit,
            cursor=cursor,
            order=order,
            extra_filters=and_(
                UsageEvent.organization_id == organization_id,
                UsageEvent.project_id == project_id,
            ),
        )

    async def list_by_date_range(
        self,
        organization_id: uuid.UUID,
        *,
        start_date: datetime,
        end_date: datetime,
        provider: str | None = None,
        model: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
        order: str = "desc",
    ) -> CursorPage[UsageEvent]:
        filters = [
            UsageEvent.organization_id == organization_id,
            UsageEvent.timestamp >= start_date,
            UsageEvent.timestamp <= end_date,
        ]
        if provider:
            filters.append(UsageEvent.provider == provider)
        if model:
            filters.append(UsageEvent.model == model)
        return await self.list_page(
            limit=limit,
            cursor=cursor,
            order=order,
            extra_filters=and_(*filters),
        )

    async def list_by_run(
        self,
        collection_run_id: uuid.UUID,
        *,
        limit: int = 20,
        cursor: str | None = None,
    ) -> CursorPage[UsageEvent]:
        return await self.list_page(
            limit=limit,
            cursor=cursor,
            extra_filters=UsageEvent.collection_run_id == collection_run_id,
        )

    async def count_by_org(self, organization_id: uuid.UUID) -> int:
        return await self.count(
            extra_filters=UsageEvent.organization_id == organization_id
        )
