"""PlaygroundExecutionRepository — EP-25.4 (AI Playground).

Pure data access for `PlaygroundExecution` history rows. Reuses
`BaseRepository`'s generic create/get/soft_delete — this class only adds
the list/search/filter queries the History panel needs.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models.playground_execution import PlaygroundExecution
from app.repositories.base_repository import BaseRepository


class PlaygroundExecutionRepository(BaseRepository[PlaygroundExecution]):
    model = PlaygroundExecution

    async def list_for_org(
        self,
        organization_id: uuid.UUID,
        *,
        user_id: uuid.UUID | None = None,
        provider: str | None = None,
        model: str | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[PlaygroundExecution], int]:
        """History list — optionally narrowed to one user (Personal accounts
        only ever see their own; Business accounts default to org-wide, see
        app/api/v1/playground.py), one provider/model, or a free-text search
        over the prompt/response text.
        """
        stmt = self._active_query().where(PlaygroundExecution.organization_id == organization_id)
        if user_id is not None:
            stmt = stmt.where(PlaygroundExecution.user_id == user_id)
        if provider is not None:
            stmt = stmt.where(PlaygroundExecution.provider == provider)
        if model is not None:
            stmt = stmt.where(PlaygroundExecution.model == model)
        if search:
            like = f"%{search}%"
            stmt = stmt.where(
                (PlaygroundExecution.user_prompt.ilike(like))
                | (PlaygroundExecution.response_text.ilike(like))
            )

        count_stmt = select(PlaygroundExecution.id).select_from(stmt.subquery())
        total_result = await self._session.execute(count_stmt)
        total = len(total_result.scalars().all())

        stmt = stmt.order_by(PlaygroundExecution.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all()), total

    async def get_for_org(
        self, organization_id: uuid.UUID, execution_id: uuid.UUID
    ) -> PlaygroundExecution | None:
        stmt = self._active_query().where(
            PlaygroundExecution.organization_id == organization_id,
            PlaygroundExecution.id == execution_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_comparison_group(
        self, organization_id: uuid.UUID, comparison_group_id: uuid.UUID
    ) -> list[PlaygroundExecution]:
        stmt = (
            self._active_query()
            .where(
                PlaygroundExecution.organization_id == organization_id,
                PlaygroundExecution.comparison_group_id == comparison_group_id,
            )
            .order_by(PlaygroundExecution.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
