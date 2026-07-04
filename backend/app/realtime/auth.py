"""WebSocket/SSE-compatible authentication — EP-19.1.

Reuses the exact validation logic the existing HTTP dependencies use
(`app.auth.tokens.decode_access_token`,
`app.services.api_key_auth_service.ApiKeyAuthService.authenticate`,
`app.auth.dependencies.ensure_org_membership`) — nothing here re-implements
JWT decoding, session-revocation checking, API-key hashing, or membership
lookup. What's new is only the "last mile": pulling the raw token out of a
WebSocket/SSE request (which can't use FastAPI's `Security(oauth2_scheme)`/
`Header()` extraction the same way an HTTP route can) and opening a
short-lived database session for the check, since a persistent connection
cannot hold one request-scoped session for its entire lifetime (see
`app/realtime/__init__.py`'s docstring).

Token extraction supports two shapes, checked in this order:
  1. `Authorization: Bearer <token>` header — works for any client that can
     set custom headers on the handshake (server-side WS clients, SSE via
     `fetch`/`httpx`/`EventSource` polyfills, this EP's own example
     clients).
  2. `?token=<token>` query parameter — the fallback every browser
     `WebSocket`/`EventSource` client needs, since neither can set custom
     headers on the underlying handshake request.

A JWT and an Organization API Key are distinguished the same way
`app.auth.api_key_auth._looks_like_api_key` already does: API keys always
start with `costorah_live_`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum

import structlog
from jwt.exceptions import DecodeError, ExpiredSignatureError, InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.exceptions import (
    ApiKeyExpiredError,
    InvalidApiKeyError,
    OrganizationSuspendedError,
)
from app.auth.rbac import Permission, has_permission
from app.auth.tokens import decode_access_token
from app.config.settings import Settings
from app.models.organization import OrganizationStatus
from app.models.user import UserStatus
from app.repositories.membership_repository import MembershipRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.session_repository import SessionRepository
from app.repositories.user_repository import UserRepository
from app.services.api_key_auth_service import ApiKeyAuthContext, ApiKeyAuthService

log = structlog.get_logger(__name__)

_API_KEY_PREFIX = "costorah_live_"

# Any active membership may open a real-time connection — it's the
# streaming equivalent of viewing the dashboard, which every role can
# already do. API keys additionally need this scope, since a key is
# minted with explicit granted permissions rather than a role.
REALTIME_REQUIRED_PERMISSION = Permission.USAGE_READ


class RealtimeAuthErrorReason(StrEnum):
    MISSING_TOKEN = "missing_token"  # noqa: S105 — enum member, not a credential
    INVALID_TOKEN = "invalid_token"  # noqa: S105
    EXPIRED_TOKEN = "expired_token"  # noqa: S105
    USER_DISABLED = "user_disabled"
    MISSING_ORGANIZATION = "missing_organization"
    ORGANIZATION_NOT_FOUND = "organization_not_found"
    ORGANIZATION_INACTIVE = "organization_inactive"
    NOT_A_MEMBER = "not_a_member"
    INSUFFICIENT_PERMISSIONS = "insufficient_permissions"
    ORGANIZATION_MISMATCH = "organization_mismatch"


class RealtimeAuthError(Exception):
    """Raised for any authentication/authorization failure on a real-time
    connection attempt. Carries enough structure for the WS gateway to
    choose a close code and the SSE endpoint to choose an HTTP status,
    without either needing to inspect the reason string."""

    def __init__(self, reason: RealtimeAuthErrorReason, message: str) -> None:
        self.reason = reason
        self.message = message
        super().__init__(message)


class PrincipalKind(StrEnum):
    USER = "user"
    API_KEY = "api_key"


@dataclass
class RealtimePrincipal:
    kind: PrincipalKind
    principal_id: uuid.UUID
    organization_id: uuid.UUID


def extract_token(*, authorization_header: str | None, query_token: str | None) -> str:
    if authorization_header:
        scheme, _, value = authorization_header.partition(" ")
        value = value.strip()
        if scheme.lower() == "bearer" and value:
            return value
    if query_token:
        return query_token
    raise RealtimeAuthError(
        RealtimeAuthErrorReason.MISSING_TOKEN,
        "No credentials provided (Authorization header or ?token= query parameter required)",
    )


def _looks_like_api_key(token: str) -> bool:
    return token.startswith(_API_KEY_PREFIX)


async def _authenticate_api_key(
    db: AsyncSession, token: str, requested_organization_id: uuid.UUID | None
) -> RealtimePrincipal:
    try:
        context: ApiKeyAuthContext = await ApiKeyAuthService(db).authenticate(token)
    except InvalidApiKeyError as exc:
        raise RealtimeAuthError(RealtimeAuthErrorReason.INVALID_TOKEN, "Invalid API Key") from exc
    except ApiKeyExpiredError as exc:
        raise RealtimeAuthError(RealtimeAuthErrorReason.EXPIRED_TOKEN, "API Key expired") from exc
    except OrganizationSuspendedError as exc:
        raise RealtimeAuthError(
            RealtimeAuthErrorReason.ORGANIZATION_INACTIVE, "Organization suspended"
        ) from exc

    if not context.has_permission(REALTIME_REQUIRED_PERMISSION):
        raise RealtimeAuthError(
            RealtimeAuthErrorReason.INSUFFICIENT_PERMISSIONS,
            f"API Key lacks the {REALTIME_REQUIRED_PERMISSION.value} scope",
        )
    if (
        requested_organization_id is not None
        and requested_organization_id != context.organization_id
    ):
        raise RealtimeAuthError(
            RealtimeAuthErrorReason.ORGANIZATION_MISMATCH,
            "organization_id does not match this API Key's organization",
        )
    return RealtimePrincipal(
        kind=PrincipalKind.API_KEY,
        principal_id=context.api_key_id,
        organization_id=context.organization_id,
    )


async def _authenticate_jwt(
    db: AsyncSession,
    token: str,
    requested_organization_id: uuid.UUID | None,
    settings: Settings,
) -> RealtimePrincipal:
    try:
        claims = decode_access_token(token, settings=settings)
    except ExpiredSignatureError as exc:
        raise RealtimeAuthError(RealtimeAuthErrorReason.EXPIRED_TOKEN, "Token expired") from exc
    except (DecodeError, InvalidTokenError) as exc:
        raise RealtimeAuthError(RealtimeAuthErrorReason.INVALID_TOKEN, "Invalid token") from exc

    user_id_str = claims.get("sub")
    session_id_str = claims.get("jti")
    if not isinstance(user_id_str, str) or not isinstance(session_id_str, str):
        raise RealtimeAuthError(RealtimeAuthErrorReason.INVALID_TOKEN, "Invalid token claims")
    try:
        user_id = uuid.UUID(user_id_str)
        session_id = uuid.UUID(session_id_str)
    except ValueError as exc:
        raise RealtimeAuthError(
            RealtimeAuthErrorReason.INVALID_TOKEN, "Invalid token claims"
        ) from exc

    db_session = await SessionRepository(db).get_active(session_id)
    if db_session is None:
        raise RealtimeAuthError(RealtimeAuthErrorReason.INVALID_TOKEN, "Session has been revoked")

    user = await UserRepository(db).get(user_id)
    if user is None:
        raise RealtimeAuthError(RealtimeAuthErrorReason.INVALID_TOKEN, "Invalid token")
    if user.status == UserStatus.DISABLED:
        raise RealtimeAuthError(RealtimeAuthErrorReason.USER_DISABLED, "Account disabled")

    if requested_organization_id is None:
        raise RealtimeAuthError(
            RealtimeAuthErrorReason.MISSING_ORGANIZATION,
            "organization_id query parameter is required",
        )

    org = await OrganizationRepository(db).get(requested_organization_id)
    if org is None:
        raise RealtimeAuthError(
            RealtimeAuthErrorReason.ORGANIZATION_NOT_FOUND, "Organization not found"
        )
    if org.status != OrganizationStatus.ACTIVE:
        raise RealtimeAuthError(
            RealtimeAuthErrorReason.ORGANIZATION_INACTIVE, "Organization is not active"
        )
    membership = await MembershipRepository(db).get_by_org_and_email(
        org_id=requested_organization_id, user_email=user.email
    )
    if membership is None:
        raise RealtimeAuthError(
            RealtimeAuthErrorReason.NOT_A_MEMBER, "Not a member of this organization"
        )
    if not has_permission(membership.role, REALTIME_REQUIRED_PERMISSION):
        raise RealtimeAuthError(
            RealtimeAuthErrorReason.INSUFFICIENT_PERMISSIONS,
            f"Role lacks the {REALTIME_REQUIRED_PERMISSION.value} permission",
        )

    return RealtimePrincipal(
        kind=PrincipalKind.USER,
        principal_id=user_id,
        organization_id=requested_organization_id,
    )


async def authenticate_realtime_connection(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    token: str,
    organization_id: uuid.UUID | None,
    settings: Settings,
) -> RealtimePrincipal:
    """Validates `token` (a JWT or an Organization API Key) and resolves the
    organization the connection is joining, opening one short-lived DB
    session for the check (never held for the connection's lifetime).
    Raises `RealtimeAuthError` on any failure — callers translate that into
    a WS close code or an HTTP status."""
    async with session_factory() as db:
        if _looks_like_api_key(token):
            principal = await _authenticate_api_key(db, token, organization_id)
        else:
            principal = await _authenticate_jwt(db, token, organization_id, settings)
        await db.commit()
        return principal
