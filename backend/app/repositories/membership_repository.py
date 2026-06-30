"""
MembershipRepository — data access for Membership entities.

Memberships link a user email to an Organization with an RBAC role.
One email may hold memberships in multiple organizations.
"""

from __future__ import annotations

import uuid

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.membership import Membership, MembershipRole
from app.models.organization import OrganizationStatus
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

    async def list_by_user_email_with_orgs(self, user_email: str) -> list[Membership]:
        """
        Return active Memberships for the given email with Organization eagerly loaded.

        Filters to ACTIVE, non-deleted organizations only.
        Uses selectinload to satisfy the lazy="raise" constraint on Membership.organization.
        """
        stmt = (
            select(Membership)
            .options(selectinload(Membership.organization))
            .where(
                Membership.deleted_at.is_(None),
                Membership.user_email == user_email,
            )
            .order_by(Membership.created_at.asc())
        )
        result = await self._session.execute(stmt)
        memberships = list(result.scalars().all())
        return [
            m
            for m in memberships
            if m.organization.deleted_at is None
            and m.organization.status == OrganizationStatus.ACTIVE
        ]

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
