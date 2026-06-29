"""FastAPI authorization dependencies — EP-05 / F-022.

Provides:
  CurrentUser          — validates the Bearer JWT and returns the authenticated User
  RequirePermission    — dependency factory: checks a Permission against the caller's role
  CurrentOrganization  — resolves ``org_id`` path param to an Organization
  CurrentMembership    — resolves (CurrentUser, CurrentOrganization) to a Membership
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import DecodeError, ExpiredSignatureError, InvalidTokenError

from app.api.deps import DbDep, get_settings
from app.auth.rbac import Permission, has_permission
from app.auth.tokens import decode_access_token
from app.config.settings import Settings
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User, UserStatus
from app.repositories.membership_repository import MembershipRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.user_repository import UserRepository

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/auth/login")

_401 = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Authentication credentials are invalid or expired",
    headers={"WWW-Authenticate": "Bearer"},
)
_403 = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="You do not have permission to perform this action",
)


async def get_current_user(
    token: Annotated[str, Security(oauth2_scheme)],
    db: DbDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    """Validate the Bearer JWT and return the corresponding active User."""
    try:
        claims = decode_access_token(token, settings=settings)
    except (ExpiredSignatureError, DecodeError, InvalidTokenError) as exc:
        raise _401 from exc

    user_id_str: Any = claims.get("sub")
    if not isinstance(user_id_str, str):
        raise _401
    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError as exc:
        raise _401 from exc

    repo = UserRepository(db)
    user = await repo.get(user_id)
    if user is None:
        raise _401

    if user.status == UserStatus.DISABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been disabled",
        )
    return user


async def _get_current_org(
    request: Request,
    db: DbDep,
) -> Organization:
    """Resolve the ``org_id`` path parameter to an active Organization."""
    org_id_str: Any = request.path_params.get("org_id")
    if org_id_str is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="org_id path parameter is required",
        )
    try:
        org_id = uuid.UUID(str(org_id_str))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="org_id must be a valid UUID",
        ) from exc
    repo = OrganizationRepository(db)
    org = await repo.get(org_id)
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )
    return org


async def _get_current_membership(
    current_user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(_get_current_org)],
    db: DbDep,
) -> Membership:
    """Return the Membership for (current_user, current_org), or 403."""
    repo = MembershipRepository(db)
    membership = await repo.get_by_org_and_email(
        org_id=org.id,
        user_email=current_user.email,
    )
    if membership is None:
        raise _403
    return membership


# ── Public type aliases for route handlers ────────────────────────────────────

CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentOrganization = Annotated[Organization, Depends(_get_current_org)]
CurrentMembership = Annotated[Membership, Depends(_get_current_membership)]


def RequirePermission(permission: Permission) -> Callable[..., Any]:  # noqa: N802
    """
    Dependency factory that enforces a specific permission.

    Usage::

        @router.get("/orgs/{org_id}/projects")
        async def list_projects(
            _: Annotated[Membership, RequirePermission(Permission.PROJECT_READ)],
        ) -> ...:
    """

    async def _check(
        membership: Annotated[Membership, Depends(_get_current_membership)],
    ) -> Membership:
        if not has_permission(membership.role, permission):
            raise _403
        return membership

    return Depends(_check)
