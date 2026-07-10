"""InvitationRepository — data access for organization invitations (EP-24.6)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.invitation import Invitation, InvitationStatus
from app.repositories.base_repository import BaseRepository


class InvitationRepository(BaseRepository[Invitation]):
    """Repository for Invitation CRUD and lifecycle queries."""

    model = Invitation

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_with_org(self, invitation_id: uuid.UUID) -> Invitation | None:
        """Return an invitation with its Organization eagerly loaded (for
        display — org name — without a second query)."""
        stmt = (
            select(Invitation)
            .options(selectinload(Invitation.organization))
            .where(Invitation.deleted_at.is_(None), Invitation.id == invitation_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_pending_by_org_and_email(
        self, org_id: uuid.UUID, email: str
    ) -> Invitation | None:
        """Return the still-pending, unexpired invitation for (org, email),
        used to enforce "no duplicate pending invitation" (EP-24.6 Part 1)."""
        now = datetime.now(UTC)
        stmt = self._active_query().where(
            and_(
                Invitation.organization_id == org_id,
                Invitation.email == email,
                Invitation.status == InvitationStatus.PENDING,
                Invitation.expires_at > now,
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_valid_by_token_hash(self, token_hash: str) -> Invitation | None:
        """Return a PENDING, unexpired invitation by token hash — the one
        lookup accept()/decline() perform. Mirrors
        ``VerificationTokenRepository.get_valid_by_hash`` exactly: replay
        protection (status flips away from PENDING on use) and expiration
        are both enforced in this single WHERE clause, not in application
        code after the fact."""
        now = datetime.now(UTC)
        stmt = self._active_query().where(
            and_(
                Invitation.token_hash == token_hash,
                Invitation.status == InvitationStatus.PENDING,
                Invitation.expires_at > now,
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_pending_by_org(self, org_id: uuid.UUID) -> list[Invitation]:
        """Return every invitation for an org that is still actionable —
        PENDING regardless of expiry (the API layer derives the "expired"
        display status from ``expires_at``, per the model's own docstring)
        — with the inviter eagerly loaded. Org invitation lists are small,
        unpaginated, matching ``MembershipRepository.list_by_org_with_users``."""
        stmt = (
            select(Invitation)
            .options(selectinload(Invitation.creator))
            .where(
                Invitation.deleted_at.is_(None),
                Invitation.organization_id == org_id,
                Invitation.status == InvitationStatus.PENDING,
            )
            .order_by(Invitation.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
