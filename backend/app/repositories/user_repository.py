"""
UserRepository — data access for User entities (EP-04, F-015).

Only data-access logic belongs here. Business rules (e.g., "a deactivated
user cannot create new memberships") belong in the service layer (EP-05+).
"""

from __future__ import annotations

import uuid

from sqlalchemy import exists, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.base_repository import BaseRepository, CursorPage


class UserRepository(BaseRepository[User]):
    """Repository for User CRUD and queries."""

    model = User

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_by_email(self, email: str) -> User | None:
        """Return the active User with the given email address, or None."""
        stmt = self._active_query().where(User.email == email)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def email_exists(self, email: str, *, exclude_id: uuid.UUID | None = None) -> bool:
        """
        Return True if the email is already taken by another active User.

        Uses SELECT EXISTS(SELECT 1 ...) to avoid fetching the full ORM row.
        Pass ``exclude_id`` when checking during an update so the user's own
        current email is not treated as a collision.
        """
        inner = (
            select(literal(1))
            .select_from(User)
            .where(
                User.deleted_at.is_(None),
                User.email == email,
            )
        )
        if exclude_id is not None:
            inner = inner.where(User.id != exclude_id)
        stmt = select(exists(inner))
        result = await self._session.execute(stmt)
        return bool(result.scalar_one())

    async def list_active(
        self,
        *,
        limit: int = 20,
        cursor: str | None = None,
        order: str = "asc",
    ) -> CursorPage[User]:
        """Return a cursor-paginated page of active (non-deactivated) users."""
        return await self.list_page(
            limit=limit,
            cursor=cursor,
            order=order,
            extra_filters=User.is_active.is_(True),
        )

    async def count_active(self) -> int:
        """Return the count of active (non-deleted, non-deactivated) users."""
        return await self.count(extra_filters=User.is_active.is_(True))
