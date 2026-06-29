"""PasswordResetTokenRepository — data access for password reset tokens (EP-05 / F-018)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy import update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.password_reset_token import PasswordResetToken
from app.repositories.base_repository import BaseRepository


class PasswordResetTokenRepository(BaseRepository[PasswordResetToken]):
    """Repository for PasswordResetToken lifecycle."""

    model = PasswordResetToken

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_valid_by_hash(self, token_hash: str) -> PasswordResetToken | None:
        """Return an unused, unexpired, non-deleted token by hash."""
        now = datetime.now(UTC)
        stmt = select(PasswordResetToken).where(
            PasswordResetToken.deleted_at.is_(None),
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > now,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_used(self, token_id: uuid.UUID) -> None:
        """Set used_at = now, preventing reuse."""
        now = datetime.now(UTC)
        stmt = (
            sql_update(PasswordResetToken)
            .where(PasswordResetToken.id == token_id)
            .values(used_at=now, updated_at=now)
        )
        await self._session.execute(stmt)

    async def invalidate_for_user(self, user_id: uuid.UUID) -> None:
        """Mark all unused tokens for a user as used (prevents parallel reset abuse)."""
        now = datetime.now(UTC)
        stmt = (
            sql_update(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user_id,
                PasswordResetToken.used_at.is_(None),
                PasswordResetToken.deleted_at.is_(None),
            )
            .values(used_at=now, updated_at=now)
        )
        await self._session.execute(stmt)

    async def get_unused_for_user(self, user_id: uuid.UUID) -> list[PasswordResetToken]:
        """Return all unexpired, unused tokens for a user (for audit purposes)."""
        now = datetime.now(UTC)
        stmt = select(PasswordResetToken).where(
            PasswordResetToken.user_id == user_id,
            PasswordResetToken.deleted_at.is_(None),
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > now,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
