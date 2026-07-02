"""
OrganizationApiKeyService — business logic for organization API keys (EP-14 Phase 1).

Responsibilities:
  - Generate a new raw key + store only its hash and a display prefix
  - Validate a presented raw key against the stored hash (Phase 2 will wire
    this into request authentication for usage ingestion)
  - List / revoke keys
  - Track last_used_at
  - Validate expiration input and requested permission scopes

The raw key is generated here and returned exactly once by the caller (the
API layer) — nothing downstream of key creation ever sees it again.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.rbac import Permission
from app.auth.tokens import hash_token
from app.db.mixins import uuid7
from app.models.organization_api_key import OrganizationApiKey
from app.repositories.organization_api_key_repository import OrganizationApiKeyRepository

KEY_PREFIX = "costorah_live_"
_PREFIX_DISPLAY_CHARS = 8

_EXPIRATION_DAYS: dict[str, int | None] = {
    "never": None,
    "30d": 30,
    "90d": 90,
}


class InvalidPermissionError(ValueError):
    """Raised when a requested permission scope is not a recognized Permission."""


class InvalidExpirationError(ValueError):
    """Raised when the requested expiration option is not recognized."""


class OrganizationApiKeyService:
    """Orchestrates API key generation, validation, listing, and revocation."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = OrganizationApiKeyRepository(session)

    # ── Validation helpers ───────────────────────────────────────────────────

    @staticmethod
    def validate_permissions(permissions: list[str]) -> list[str]:
        """Return the permission list unchanged if every scope is a known Permission.

        Raises InvalidPermissionError naming the first unrecognized scope.
        """
        valid = {p.value for p in Permission}
        for scope in permissions:
            if scope not in valid:
                raise InvalidPermissionError(scope)
        return permissions

    @staticmethod
    def resolve_expiration(expiration: str) -> datetime | None:
        """Translate 'never' | '30d' | '90d' into an absolute expires_at, or None."""
        if expiration not in _EXPIRATION_DAYS:
            raise InvalidExpirationError(expiration)
        days = _EXPIRATION_DAYS[expiration]
        if days is None:
            return None
        return datetime.now(UTC) + timedelta(days=days)

    @staticmethod
    def is_expired(key: OrganizationApiKey) -> bool:
        """Return True when this key has an expiry in the past."""
        return key.expires_at is not None and key.expires_at <= datetime.now(UTC)

    # ── Key generation ───────────────────────────────────────────────────────

    @staticmethod
    def _generate_raw_key() -> tuple[str, str]:
        """Return (raw_key, display_prefix). The raw key is never persisted."""
        secret = secrets.token_urlsafe(32)
        raw_key = f"{KEY_PREFIX}{secret}"
        display_prefix = f"{KEY_PREFIX}{secret[:_PREFIX_DISPLAY_CHARS]}"
        return raw_key, display_prefix

    async def create_key(
        self,
        *,
        organization_id: uuid.UUID,
        name: str,
        description: str | None,
        permissions: list[str],
        expiration: str,
        created_by: uuid.UUID,
    ) -> tuple[OrganizationApiKey, str]:
        """
        Generate, hash, and persist a new API key.

        Returns (record, raw_key). The caller (API layer) must return
        raw_key to the client in this response only — it is never
        retrievable again.
        """
        self.validate_permissions(permissions)
        expires_at = self.resolve_expiration(expiration)
        raw_key, display_prefix = self._generate_raw_key()

        record = OrganizationApiKey()
        record.id = uuid7()
        record.organization_id = organization_id
        record.name = name
        record.description = description
        record.key_prefix = display_prefix
        record.key_hash = hash_token(raw_key)
        record.permissions = permissions
        record.created_by = created_by
        record.expires_at = expires_at

        created = await self._repo.create(record)
        return created, raw_key

    # ── Reads ─────────────────────────────────────────────────────────────────

    async def list_keys(self, organization_id: uuid.UUID) -> list[OrganizationApiKey]:
        return await self._repo.list(organization_id)

    async def validate_key(self, raw_key: str) -> OrganizationApiKey | None:
        """
        Return the active, non-expired key matching `raw_key`, or None.

        Does not update last_used_at — callers that authenticate a request
        with this key should follow up with touch_last_used().
        """
        key = await self._repo.get_by_hash(hash_token(raw_key))
        if key is None or self.is_expired(key):
            return None
        return key

    async def touch_last_used(self, key: OrganizationApiKey) -> OrganizationApiKey:
        return await self._repo.update_last_used(key)

    # ── Revocation ────────────────────────────────────────────────────────────

    async def delete_key(
        self,
        key: OrganizationApiKey,
        *,
        deleted_by: uuid.UUID | None = None,
    ) -> None:
        await self._repo.delete(key, deleted_by=deleted_by)
