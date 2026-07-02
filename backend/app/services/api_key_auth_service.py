"""
ApiKeyAuthService — authenticates inbound requests via Organization API Keys (EP-15).

Builds entirely on the EP-14 API key surface (OrganizationApiKeyRepository,
OrganizationApiKeyService, the OrganizationApiKey model) without modifying
any of it. This module owns only the *authentication* orchestration: hash
lookup, expiry check, organization-status check, and the last_used_at touch
— i.e. everything EP-14 intentionally left unwired ("Phase 2 will wire this
into request authentication").

Query budget per authenticate() call: exactly 2 SELECTs (key by hash,
organization by id) + 1 UPDATE (last_used_at). No N+1s, no repeated lookups
within a request — callers should resolve once via the CurrentApiKey
dependency and reuse the returned ApiKeyAuthContext for the rest of the
request instead of authenticating again.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.exceptions import (
    ApiKeyExpiredError,
    InvalidApiKeyError,
    OrganizationSuspendedError,
)
from app.auth.rbac import Permission
from app.auth.tokens import hash_token
from app.models.organization import Organization, OrganizationStatus
from app.models.organization_api_key import OrganizationApiKey
from app.repositories.organization_api_key_repository import OrganizationApiKeyRepository
from app.repositories.organization_repository import OrganizationRepository
from app.services.organization_api_key_service import OrganizationApiKeyService


@dataclass(frozen=True, slots=True)
class ApiKeyAuthContext:
    """
    Everything an authenticated-by-API-key request needs, resolved once.

    Exposes the same shape callers would otherwise need a second database
    round-trip to reconstruct: the organization, the key record, the
    permission scopes it was granted, and who created it.
    """

    api_key: OrganizationApiKey
    organization: Organization

    @property
    def organization_id(self) -> uuid.UUID:
        return self.organization.id

    @property
    def api_key_id(self) -> uuid.UUID:
        return self.api_key.id

    @property
    def created_by(self) -> uuid.UUID | None:
        return self.api_key.created_by

    @property
    def permissions(self) -> frozenset[Permission]:
        """Permission scopes granted to this key, parsed from stored strings.

        Silently drops any value that no longer maps to a known Permission
        (e.g. a permission removed from the enum after the key was created)
        rather than failing the whole request — an unrecognized scope simply
        grants nothing, which is the fail-closed behavior we want.
        """
        parsed: set[Permission] = set()
        for value in self.api_key.permissions:
            try:
                parsed.add(Permission(value))
            except ValueError:
                continue
        return frozenset(parsed)

    def has_permission(self, permission: Permission) -> bool:
        return permission in self.permissions


class ApiKeyAuthService:
    """Authenticates a raw API key and resolves its request context."""

    def __init__(self, session: AsyncSession) -> None:
        self._key_repo = OrganizationApiKeyRepository(session)
        self._org_repo = OrganizationRepository(session)

    async def authenticate(self, raw_key: str) -> ApiKeyAuthContext:
        """
        Validate `raw_key` end-to-end and return its resolved context.

        Raises (never returns None — callers get an unambiguous exception
        per failure class, mapped to HTTP responses by the dependency layer):
          InvalidApiKeyError        — unknown hash, or the key was soft-deleted
                                       (repository queries already exclude
                                       deleted_at IS NOT NULL rows, so this
                                       and "never existed" are indistinguishable
                                       by design)
          ApiKeyExpiredError        — hash matched, but expires_at has passed
          OrganizationSuspendedError — the owning organization is missing or
                                       not ACTIVE (suspended/archived)
        """
        key_hash = hash_token(raw_key)
        key = await self._key_repo.get_by_hash(key_hash)
        if key is None:
            raise InvalidApiKeyError

        if OrganizationApiKeyService.is_expired(key):
            raise ApiKeyExpiredError

        org = await self._org_repo.get(key.organization_id)
        if org is None or org.status != OrganizationStatus.ACTIVE:
            raise OrganizationSuspendedError

        await self._key_repo.update_last_used(key)

        return ApiKeyAuthContext(api_key=key, organization=org)
