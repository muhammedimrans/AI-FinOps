"""
FastAPI authorization dependencies for Organization API Key authentication (EP-15).

Provides:
  CurrentApiKey            — validates `Authorization: Bearer costorah_live_...`
                              and returns the resolved ApiKeyAuthContext
  RequireApiKeyPermission  — dependency factory: checks a Permission against
                              the key's granted scopes
  MembershipOrApiKey       — accepts EITHER a JWT session (org membership) OR
                              an Organization API Key, for the small set of
                              endpoints that must serve both human dashboard
                              traffic and machine/integration callers

This module never re-implements hashing, expiry, or CRUD — all of that stays
in EP-14 (OrganizationApiKeyRepository / OrganizationApiKeyService) and the
new ApiKeyAuthService, which this module only calls.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Annotated, Any, cast

import structlog
from fastapi import Depends, Header, HTTPException, Request, status

from app.api.deps import DbDep
from app.auth.dependencies import (
    _get_current_membership,
    _get_current_org,
    get_current_user,
    oauth2_scheme,
)
from app.auth.exceptions import (
    ApiKeyExpiredError,
    InsufficientApiKeyPermissionsError,
    InvalidApiKeyError,
    OrganizationSuspendedError,
)
from app.auth.rbac import Permission, has_permission
from app.config.settings import get_settings
from app.models.membership import Membership
from app.models.user import User
from app.services.api_key_auth_service import ApiKeyAuthContext, ApiKeyAuthService

logger = structlog.get_logger(__name__)

_401_INVALID = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid API Key",
)
_401_EXPIRED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="API Key expired",
)
_403_SUSPENDED = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="Organization suspended",
)
_403_INSUFFICIENT_PERMISSIONS = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="Insufficient API Key permissions",
)

_API_KEY_PREFIX = "costorah_live_"


def _extract_bearer_token(authorization: str | None) -> str:
    """
    Return the token from an `Authorization: Bearer <token>` header.

    Raises InvalidApiKeyError uniformly for every malformed shape (missing
    header, missing/misspelled Bearer scheme, empty token) — the failure
    reason is never distinguishable in the response.
    """
    if not authorization:
        raise InvalidApiKeyError
    scheme, _, token = authorization.partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token:
        raise InvalidApiKeyError
    return token


def _looks_like_api_key(authorization: str) -> bool:
    """Cheap, no-DB sniff used only to route a request to the right auth path."""
    _, _, token = authorization.partition(" ")
    return token.strip().startswith(_API_KEY_PREFIX)


async def _authenticate_api_key(db: DbDep, authorization: str | None) -> ApiKeyAuthContext:
    try:
        raw_key = _extract_bearer_token(authorization)
        context = await ApiKeyAuthService(db).authenticate(raw_key)
    except InvalidApiKeyError as exc:
        raise _401_INVALID from exc
    except ApiKeyExpiredError as exc:
        raise _401_EXPIRED from exc
    except OrganizationSuspendedError as exc:
        raise _403_SUSPENDED from exc

    logger.info(
        "api_key_authenticated",
        organization_id=str(context.organization_id),
        organization=context.organization.slug,
        key_prefix=context.api_key.key_prefix,
        api_key_id=str(context.api_key_id),
    )
    return context


async def get_current_api_key(
    db: DbDep,
    authorization: Annotated[str | None, Header()] = None,
) -> ApiKeyAuthContext:
    """Authenticate an inbound request via `Authorization: Bearer costorah_live_...`."""
    return await _authenticate_api_key(db, authorization)


CurrentApiKey = Annotated[ApiKeyAuthContext, Depends(get_current_api_key)]


def RequireApiKeyPermission(permission: Permission) -> Callable[..., Any]:  # noqa: N802
    """
    Dependency factory enforcing a specific permission scope on the API key.

    Usage::

        @router.get("/organizations/{org_id}/usage")
        async def list_usage(
            current_api_key: Annotated[
                ApiKeyAuthContext, RequireApiKeyPermission(Permission.USAGE_READ)
            ],
        ) -> ...:
    """

    async def _check(context: CurrentApiKey) -> ApiKeyAuthContext:
        if not context.has_permission(permission):
            raise InsufficientApiKeyPermissionsError
        return context

    async def _check_and_map(context: CurrentApiKey) -> ApiKeyAuthContext:
        try:
            return await _check(context)
        except InsufficientApiKeyPermissionsError as exc:
            raise _403_INSUFFICIENT_PERMISSIONS from exc

    # FastAPI's Depends() is typed to return `Any` by design; cast to the
    # documented factory return type rather than letting `Any` leak out.
    return cast("Callable[..., Any]", Depends(_check_and_map))


# ── Dual auth: JWT membership OR API key ────────────────────────────────────
#
# A small number of endpoints (currently just GET .../api-keys, per EP-15's
# own success criterion) must serve both the dashboard, which authenticates
# with a JWT session, and external integrations, which authenticate with an
# Organization API Key. Routing is a cheap prefix sniff on the token itself
# (real API keys always start with "costorah_live_"); everything else falls
# through to the existing JWT + membership dependency chain unchanged.


async def _resolve_current_user(request: Request, db: DbDep) -> User:
    """
    Resolve the JWT-authenticated user for the fallback (non-API-key) path.

    get_current_user is normally injected via Depends() and therefore
    transparently honors app.dependency_overrides[get_current_user] (used
    throughout the test suite to fake a caller without a real JWT). Calling
    it directly here — necessary so an API key can short-circuit the JWT
    path entirely — would silently bypass that override, so it's checked
    explicitly first.
    """
    override = request.app.dependency_overrides.get(get_current_user)
    if override is not None:
        return cast("User", await override())
    token = await oauth2_scheme(request)
    if token is None:
        # oauth2_scheme has auto_error=True, so it raises 401 itself before
        # ever returning None — this satisfies the type checker only.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return await get_current_user(token=token, db=db, settings=get_settings())


async def get_membership_or_api_key(
    request: Request,
    db: DbDep,
) -> Membership | ApiKeyAuthContext:
    header = request.headers.get("Authorization")
    if header and _looks_like_api_key(header):
        return await _authenticate_api_key(db, header)

    user = await _resolve_current_user(request, db)
    org = await _get_current_org(request=request, db=db)
    return await _get_current_membership(current_user=user, org=org, db=db)


def RequireMembershipOrApiKeyPermission(  # noqa: N802
    permission: Permission,
) -> Callable[..., Any]:
    """
    Dependency factory accepting either auth mechanism, enforcing `permission`
    under whichever RBAC mapping applies (role-based for a membership,
    granted-scopes for an API key), and — for API keys — verifying the key's
    organization matches the `org_id` path parameter so a key from one
    organization can never read another's resources.
    """

    async def _check(
        request: Request,
        principal: Annotated[Membership | ApiKeyAuthContext, Depends(get_membership_or_api_key)],
    ) -> Membership | ApiKeyAuthContext:
        if isinstance(principal, ApiKeyAuthContext):
            org_id_str = request.path_params.get("org_id")
            if org_id_str is None or principal.organization_id != uuid.UUID(str(org_id_str)):
                raise _401_INVALID
            if not principal.has_permission(permission):
                raise _403_INSUFFICIENT_PERMISSIONS
            return principal

        if not has_permission(principal.role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )
        return principal

    return cast("Callable[..., Any]", Depends(_check))
