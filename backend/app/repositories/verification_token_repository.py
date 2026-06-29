"""VerificationTokenRepository — data access for email verification tokens (EP-05 / F-019)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy import update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.verification_token import VerificationToken
from app.repositories.base_repository import BaseRepository


class VerificationTokenRepository(BaseRepository[VerificationToken]):
    """Repository for VerificationToken lifecycle."""

    model = VerificationToken

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_valid_by_hash(self, token_hash: str) -> VerificationToken | None:
        """Return an unused, unexpired, non-deleted token by hash."""
        now = datetime.now(UTC)
        stmt = select(VerificationToken).where(
            VerificationToken.deleted_at.is_(None),
            VerificationToken.token_hash == token_hash,
            VerificationToken.used_at.is_(None),
            VerificationToken.expires_at > now,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_used(self, token_id: uuid.UUID) -> None:
        """Set used_at = now, preventing reuse."""
        now = datetime.now(UTC)
        stmt = (
            sql_update(VerificationToken)
            .where(VerificationToken.id == token_id)
            .values(used_at=now, updated_at=now)
        )
        await self._session.execute(stmt)
