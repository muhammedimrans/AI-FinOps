"""RBAC introspection API — EP-13.

Endpoints:
  GET /v1/rbac/roles       — every role and the permissions it grants
  GET /v1/rbac/permissions — every permission defined in the system

The role→permission mapping itself (app/auth/rbac.py) has existed since
EP-05 and is enforced on every permission-checked endpoint via
RequirePermission. These endpoints only expose that existing, static
mapping for display — e.g. an org admin reviewing what each role can do
before assigning it. They carry no per-organization data, so no org-scoped
authorization is needed beyond being an authenticated user.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.auth.dependencies import CurrentUser
from app.auth.rbac import ROLE_PERMISSIONS
from app.models.membership import MembershipRole
from app.schemas.rbac import PermissionInfo, PermissionsResponse, RoleInfo, RolesResponse

router = APIRouter(prefix="/rbac", tags=["rbac"])

_ROLE_LABELS: dict[MembershipRole, str] = {
    MembershipRole.OWNER: "Owner",
    MembershipRole.ADMIN: "Admin",
    MembershipRole.MEMBER: "Member",
    MembershipRole.VIEWER: "Viewer",
}

# Display order — most privileged first, matching how the RBAC engine grants
# permissions (OWNER implies everything ADMIN has, etc.).
_ROLE_ORDER: list[MembershipRole] = [
    MembershipRole.OWNER,
    MembershipRole.ADMIN,
    MembershipRole.MEMBER,
    MembershipRole.VIEWER,
]


@router.get(
    "/roles",
    response_model=RolesResponse,
    summary="List every role and the permissions it grants",
)
async def list_roles(_user: CurrentUser) -> RolesResponse:
    return RolesResponse(
        roles=[
            RoleInfo(
                role=role.value,
                label=_ROLE_LABELS[role],
                permissions=sorted(p.value for p in ROLE_PERMISSIONS.get(role, frozenset())),
            )
            for role in _ROLE_ORDER
        ]
    )


@router.get(
    "/permissions",
    response_model=PermissionsResponse,
    summary="List every permission defined in the system",
)
async def list_permissions(_user: CurrentUser) -> PermissionsResponse:
    all_permissions = sorted({p.value for perms in ROLE_PERMISSIONS.values() for p in perms})
    items = []
    for value in all_permissions:
        domain, _, action = value.partition(":")
        items.append(PermissionInfo(permission=value, domain=domain, action=action))
    return PermissionsResponse(permissions=items)
