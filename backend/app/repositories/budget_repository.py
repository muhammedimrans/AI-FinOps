"""BudgetRepository — EP-24.2.

Pure data access for the `Budget` entity. All spend aggregation for a
budget's scope+period is done elsewhere (UsageCostRecordRepository, via
app/budgets/service.py) — this repository only reads/writes Budget rows.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models.budget import Budget
from app.repositories.base_repository import BaseRepository


class BudgetRepository(BaseRepository[Budget]):
    model = Budget

    async def list_for_org(
        self, organization_id: uuid.UUID, *, enabled_only: bool = False
    ) -> list[Budget]:
        stmt = self._active_query().where(Budget.organization_id == organization_id)
        if enabled_only:
            stmt = stmt.where(Budget.enabled.is_(True))
        stmt = stmt.order_by(Budget.created_at.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_enabled_for_org(self, organization_id: uuid.UUID) -> list[Budget]:
        """The set of budgets `BudgetEvaluationService` evaluates for one
        organization after a usage sync (EP-24.2)."""
        return await self.list_for_org(organization_id, enabled_only=True)

    async def get_for_org(self, organization_id: uuid.UUID, budget_id: uuid.UUID) -> Budget | None:
        stmt = self._active_query().where(
            Budget.organization_id == organization_id, Budget.id == budget_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_enabled_for_all_orgs(self) -> list[Budget]:
        """Every enabled budget across every organization — used by the
        scheduler-driven evaluation path when a sync run needs to know
        which orgs have budgets worth checking (EP-24.2)."""
        stmt = self._active_query().where(Budget.enabled.is_(True))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def distinct_org_ids_with_enabled_budgets(self) -> list[uuid.UUID]:
        stmt = (
            select(Budget.organization_id)
            .where(Budget.deleted_at.is_(None), Budget.enabled.is_(True))
            .distinct()
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
