"""
OrganizationApiKeyRepository — data access for OrganizationApiKey entities (EP-14).

Only data-access logic belongs here. Key generation, hashing, and expiry
rules belong in the service layer.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization_api_key import OrganizationApiKey
from app.repositories.base_repository import BaseRepository


class OrganizationApiKeyRepository(BaseRepository[OrganizationApiKey]):
    """Repository for OrganizationApiKey CRUD and queries."""

    model = OrganizationApiKey

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def list(self, org_id: uuid.UUID) -> list[OrganizationApiKey]:
        """Return every active API key for an org, newest first.

        Org key lists are small (tens, not thousands) so this is unpaginated,
        matching MembershipRepository.list_by_org_with_users.
        """
        stmt = (
            select(OrganizationApiKey)
            .where(
                OrganizationApiKey.deleted_at.is_(None),
                OrganizationApiKey.organization_id == org_id,
            )
            .order_by(OrganizationApiKey.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_hash(self, key_hash: str) -> OrganizationApiKey | None:
        """Return the active key matching this SHA-256 hash, or None.

        Used to validate an inbound key on each authenticated request
        (Phase 2 — usage ingestion). key_hash is uniquely indexed.
        """
        stmt = self._active_query().where(OrganizationApiKey.key_hash == key_hash)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete(
        self,
        instance: OrganizationApiKey,
        deleted_by: uuid.UUID | None = None,
    ) -> OrganizationApiKey:
        """Soft-delete (revoke) an API key."""
        return await self.soft_delete(instance, deleted_by=deleted_by)

    async def update_last_used(self, instance: OrganizationApiKey) -> OrganizationApiKey:
        """Stamp last_used_at with the current time."""
        return await self.update(instance, last_used_at=datetime.now(UTC))
