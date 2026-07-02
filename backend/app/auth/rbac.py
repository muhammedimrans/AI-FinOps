"""RBAC permission model — EP-05 / F-021.

Roles are defined by MembershipRole (EP-04). This module maps each role to
its allowed Permission set and provides a single entry-point for permission
checks so the mapping lives in one place.

Permission string format: ``<domain>:<action>``
"""

from __future__ import annotations

import enum

from app.models.membership import MembershipRole


class Permission(enum.StrEnum):
    """Granular permissions used in FastAPI authorization dependencies."""

    # Organization
    ORG_READ = "org:read"
    ORG_WRITE = "org:write"
    ORG_DELETE = "org:delete"
    ORG_MANAGE_MEMBERS = "org:manage_members"

    # Project
    PROJECT_READ = "project:read"
    PROJECT_WRITE = "project:write"
    PROJECT_DELETE = "project:delete"

    # Provider connections
    PROVIDER_READ = "provider:read"
    PROVIDER_WRITE = "provider:write"
    PROVIDER_DELETE = "provider:delete"

    # Usage & billing
    USAGE_READ = "usage:read"
    USAGE_WRITE = "usage:write"
    BILLING_READ = "billing:read"
    BILLING_WRITE = "billing:write"

    # Organization API keys (EP-14)
    API_KEY_READ = "api_key:read"
    API_KEY_WRITE = "api_key:write"


# Every permission granted to each role. Higher roles include all lower-role permissions.
_OWNER_PERMS: frozenset[Permission] = frozenset(Permission)

_ADMIN_PERMS: frozenset[Permission] = frozenset(
    [
        Permission.ORG_READ,
        Permission.ORG_WRITE,
        Permission.ORG_MANAGE_MEMBERS,
        Permission.PROJECT_READ,
        Permission.PROJECT_WRITE,
        Permission.PROJECT_DELETE,
        Permission.PROVIDER_READ,
        Permission.PROVIDER_WRITE,
        Permission.PROVIDER_DELETE,
        Permission.USAGE_READ,
        Permission.USAGE_WRITE,
        Permission.BILLING_READ,
        Permission.API_KEY_READ,
        Permission.API_KEY_WRITE,
    ]
)

_MEMBER_PERMS: frozenset[Permission] = frozenset(
    [
        Permission.ORG_READ,
        Permission.PROJECT_READ,
        Permission.PROJECT_WRITE,
        Permission.PROVIDER_READ,
        Permission.USAGE_READ,
        Permission.API_KEY_READ,
    ]
)

_VIEWER_PERMS: frozenset[Permission] = frozenset(
    [
        Permission.ORG_READ,
        Permission.PROJECT_READ,
        Permission.PROVIDER_READ,
        Permission.USAGE_READ,
        Permission.API_KEY_READ,
    ]
)

ROLE_PERMISSIONS: dict[MembershipRole, frozenset[Permission]] = {
    MembershipRole.OWNER: _OWNER_PERMS,
    MembershipRole.ADMIN: _ADMIN_PERMS,
    MembershipRole.MEMBER: _MEMBER_PERMS,
    MembershipRole.VIEWER: _VIEWER_PERMS,
}


def has_permission(role: MembershipRole, permission: Permission) -> bool:
    """Return True when the given role grants the given permission."""
    return permission in ROLE_PERMISSIONS.get(role, frozenset())


def get_permissions(role: MembershipRole) -> frozenset[Permission]:
    """Return the complete permission set for the given role."""
    return ROLE_PERMISSIONS.get(role, frozenset())
