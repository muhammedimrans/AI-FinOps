"""SessionRepository — data access for Session entities (EP-05 / F-020)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy import update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import Session
from app.repositories.base_repository import BaseRepository


class SessionRepository(BaseRepository[Session]):
    """Repository for Session CRUD and lifecycle management."""

    model = Session

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_active(self, session_id: uuid.UUID) -> Session | None:
        """Return the non-revoked, non-expired, non-deleted Session by id.

        Used by get_current_user to reject access tokens whose session was
        revoked (logout, password reset) before the JWT itself expires.
        """
        now = datetime.now(UTC)
        stmt = self._active_query().where(
            Session.id == session_id,
            Session.revoked_at.is_(None),
            Session.expires_at > now,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_by_token_hash(self, token_hash: str) -> Session | None:
        """Return a non-revoked, non-expired, non-deleted Session by refresh token hash."""
        now = datetime.now(UTC)
        stmt = self._active_query().where(
            Session.refresh_token_hash == token_hash,
            Session.revoked_at.is_(None),
            Session.expires_at > now,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def revoke(self, session_id: uuid.UUID) -> None:
        """Set revoked_at = now for the given session."""
        now = datetime.now(UTC)
        stmt = (
            sql_update(Session)
            .where(Session.id == session_id, Session.deleted_at.is_(None))
            .values(revoked_at=now, updated_at=now)
        )
        await self._session.execute(stmt)

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> None:
        """Revoke every active session belonging to a user (e.g. on password reset)."""
        now = datetime.now(UTC)
        stmt = (
            sql_update(Session)
            .where(
                Session.user_id == user_id,
                Session.revoked_at.is_(None),
                Session.deleted_at.is_(None),
            )
            .values(revoked_at=now, updated_at=now)
        )
        await self._session.execute(stmt)

    async def revoke_all_for_user_except(
        self, user_id: uuid.UUID, keep_session_id: uuid.UUID
    ) -> None:
        """Revoke every active session for a user except one (EP-22.2 change-password).

        Used so changing your password from the current session doesn't log
        you out of the device you're using, while still invalidating every
        other session — the same "log out everywhere else" behavior most
        products give a password change.
        """
        now = datetime.now(UTC)
        stmt = (
            sql_update(Session)
            .where(
                Session.user_id == user_id,
                Session.id != keep_session_id,
                Session.revoked_at.is_(None),
                Session.deleted_at.is_(None),
            )
            .values(revoked_at=now, updated_at=now)
        )
        await self._session.execute(stmt)

    async def rotate(
        self,
        session_id: uuid.UUID,
        *,
        new_token_hash: str,
        new_expires_at: datetime,
    ) -> None:
        """Replace the refresh token hash and extend expiry (refresh token rotation)."""
        now = datetime.now(UTC)
        stmt = (
            sql_update(Session)
            .where(Session.id == session_id, Session.deleted_at.is_(None))
            .values(
                refresh_token_hash=new_token_hash,
                expires_at=new_expires_at,
                updated_at=now,
            )
        )
        await self._session.execute(stmt)

    async def list_active_for_user(self, user_id: uuid.UUID) -> list[Session]:
        """Return all non-revoked, non-expired sessions for a user."""
        now = datetime.now(UTC)
        stmt = select(Session).where(
            Session.user_id == user_id,
            Session.deleted_at.is_(None),
            Session.revoked_at.is_(None),
            Session.expires_at > now,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
