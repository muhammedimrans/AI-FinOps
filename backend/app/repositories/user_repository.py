"""
UserRepository - data access for User entities (EP-04 / EP-04.1).

Only data-access logic belongs here. Business rules (e.g., "a disabled
user cannot create new memberships") belong in the service layer (EP-05+).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import exists, func, literal, or_, select
from sqlalchemy import update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserStatus
from app.repositories.base_repository import BaseRepository, CursorPage


class UserRepository(BaseRepository[User]):
    """Repository for User CRUD and queries."""

    model = User

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    # ── Lookups ───────────────────────────────────────────────────────────────

    async def get_by_email(self, email: str) -> User | None:
        """Return the active (non-deleted) User with the given email, or None."""
        stmt = self._active_query().where(User.email == email)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> User | None:
        """Return the active (non-deleted) User with the given username, or None."""
        stmt = self._active_query().where(User.username == username)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_google_sub(self, google_sub: str) -> User | None:
        """Return the active (non-deleted) User with the given Google `sub`, or None.

        EP-24.5 — the correct join key for "has this Google account logged in
        before," since a Google account's *email* can technically change
        while its ``sub`` never does.
        """
        stmt = self._active_query().where(User.google_sub == google_sub)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    # ── Existence checks ──────────────────────────────────────────────────────

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
            .where(User.deleted_at.is_(None), User.email == email)
        )
        if exclude_id is not None:
            inner = inner.where(User.id != exclude_id)
        stmt = select(exists(inner))
        result = await self._session.execute(stmt)
        return bool(result.scalar_one())

    async def username_exists(self, username: str, *, exclude_id: uuid.UUID | None = None) -> bool:
        """
        Return True if the username is already taken by another active User.

        Pass ``exclude_id`` when checking during profile updates so the user's
        own current username is not treated as a collision.
        """
        inner = (
            select(literal(1))
            .select_from(User)
            .where(User.deleted_at.is_(None), User.username == username)
        )
        if exclude_id is not None:
            inner = inner.where(User.id != exclude_id)
        stmt = select(exists(inner))
        result = await self._session.execute(stmt)
        return bool(result.scalar_one())

    # ── List / Search ─────────────────────────────────────────────────────────

    async def list_active(
        self,
        *,
        limit: int = 20,
        cursor: str | None = None,
        order: str = "asc",
    ) -> CursorPage[User]:
        """Return a cursor-paginated page of ACTIVE users (status == active)."""
        return await self.list_page(
            limit=limit,
            cursor=cursor,
            order=order,
            extra_filters=User.status == UserStatus.ACTIVE,
        )

    async def search_users(
        self,
        query: str,
        *,
        limit: int = 20,
        cursor: str | None = None,
    ) -> CursorPage[User]:
        """
        Case-insensitive substring search across email, username, and display_name.

        Returns non-deleted users regardless of status, ordered by created_at ASC.
        Intended for administrative user-lookup endpoints.
        """
        pattern = f"%{query}%"
        extra_filter = or_(
            User.email.ilike(pattern),
            User.username.ilike(pattern),
            User.display_name.ilike(pattern),
        )
        return await self.list_page(limit=limit, cursor=cursor, extra_filters=extra_filter)

    # ── Counts ────────────────────────────────────────────────────────────────

    async def count_active(self) -> int:
        """Return the count of non-deleted ACTIVE users (status == active)."""
        return await self.count(extra_filters=User.status == UserStatus.ACTIVE)

    # ── Writes ────────────────────────────────────────────────────────────────

    async def update_last_login(self, user_id: uuid.UUID, *, provider: str | None = None) -> None:
        """
        Record the current UTC timestamp as ``last_login_at`` for the given user.

        Uses a targeted UPDATE statement rather than loading the full ORM row
        to keep the operation cheap in high-traffic authentication flows.
        Also bumps ``updated_at`` because the ORM ``onupdate`` hook does not
        fire for bulk-style UPDATE statements.

        ``provider`` (EP-24.5) — when given, also sets ``last_login_provider``
        ("password" | "google") in the same statement, so Settings' "Last
        login provider" display (Part 7) is always the outcome of the most
        recent successful authentication.
        """
        now = datetime.now(UTC)
        values: dict[str, object] = {"last_login_at": now, "updated_at": now}
        if provider is not None:
            values["last_login_provider"] = provider
        stmt = (
            sql_update(User).where(User.id == user_id, User.deleted_at.is_(None)).values(**values)
        )
        await self._session.execute(stmt)

    # ── Aggregates ────────────────────────────────────────────────────────────

    async def count_by_status(self, status: UserStatus) -> int:
        """Return the count of non-deleted users with the given status."""
        stmt = (
            select(func.count())
            .select_from(User)
            .where(User.deleted_at.is_(None), User.status == status)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()
