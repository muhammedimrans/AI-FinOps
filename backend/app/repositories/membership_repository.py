"""
MembershipRepository — data access for Membership entities.

Memberships link a user email to an Organization with an RBAC role.
One email may hold memberships in multiple organizations.
"""

from __future__ import annotations

import uuid

from sqlalchemy import and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.membership import Membership, MembershipRole
from app.repositories.base_repository import BaseRepository, CursorPage


class MembershipRepository(BaseRepository[Membership]):
    """Repository for Membership CRUD and queries."""

    model = Membership

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_by_org_and_email(
        self,
        org_id: uuid.UUID,
        user_email: str,
    ) -> Membership | None:
        """
        Return the active Membership for (org, email), or None.
        Uses the unique index on (organization_id, user_email).
        """
        stmt = self._active_query().where(
            and_(
                Membership.organization_id == org_id,
                Membership.user_email == user_email,
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_org(
        self,
        org_id: uuid.UUID,
        *,
        limit: int = 20,
        cursor: str | None = None,
        order: str = "asc",
    ) -> CursorPage[Membership]:
        """Return all active Memberships for the given Organization."""
        return await self.list_page(
            limit=limit,
            cursor=cursor,
            order=order,
            extra_filters=Membership.organization_id == org_id,
        )

    async def list_by_email(
        self,
        user_email: str,
        *,
        limit: int = 20,
        cursor: str | None = None,
        order: str = "asc",
    ) -> CursorPage[Membership]:
        """Return all active Memberships for the given email (across all orgs)."""
        return await self.list_page(
            limit=limit,
            cursor=cursor,
            order=order,
            extra_filters=Membership.user_email == user_email,
        )

    async def list_by_org_and_role(
        self,
        org_id: uuid.UUID,
        role: MembershipRole,
        *,
        limit: int = 20,
        cursor: str | None = None,
        order: str = "asc",
    ) -> CursorPage[Membership]:
        """Return active Memberships for (org, role)."""
        return await self.list_page(
            limit=limit,
            cursor=cursor,
            order=order,
            extra_filters=and_(
                Membership.organization_id == org_id,
                Membership.role == role,
            ),
        )
