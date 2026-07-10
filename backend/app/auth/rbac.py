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
    # EP-24.6 — OWNER-only, mirrors ORG_DELETE's "most irreversible actions
    # require the most senior role" precedent below. Never granted to
    # _ADMIN_PERMS; automatically included in _OWNER_PERMS (= frozenset(Permission)).
    ORG_TRANSFER_OWNERSHIP = "org:transfer_ownership"

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

    # Alerts & notifications (EP-19.3)
    NOTIFICATION_READ = "notification:read"
    NOTIFICATION_WRITE = "notification:write"


# Every permission granted to each role. Higher roles include all lower-role permissions.
#
# Permission-consistency invariant (audited, EP-24): for any resource a role
# can create/write, that same role must also be able to delete the
# resources it created, unless a documented exception applies below. This
# codebase had exactly one violation of that invariant — MEMBER held
# PROJECT_WRITE without PROJECT_DELETE, so a MEMBER could create a project
# but never remove it — fixed by adding PROJECT_DELETE to _MEMBER_PERMS.
#
# Documented exceptions (deliberately asymmetric, not oversights):
#   - ORG_TRANSFER_OWNERSHIP (EP-24.6) is OWNER-only, granted to no other
#     role — an ADMIN can manage members (invite/role-change/remove) but
#     can never make themselves or anyone else the OWNER; only the current
#     OWNER can hand that role to someone else.
#   - ORG_DELETE is OWNER-only even though ADMIN holds ORG_WRITE. Deleting
#     an organization is categorically more destructive than any other
#     delete in this table — it cascades to every project, provider
#     connection, API key, and membership the org owns, and cannot target
#     "just the thing I created" the way PROJECT_DELETE/PROVIDER_DELETE do.
#     Reserving it for OWNER mirrors this module's existing "only an OWNER
#     may grant the OWNER role" precedent (app/api/v1/organizations.py) —
#     the account's most irreversible actions require its most senior role.
#   - Every other WRITE/DELETE pair (PROJECT, PROVIDER) is granted or
#     withheld together per role — MEMBER has neither PROVIDER_WRITE nor
#     PROVIDER_DELETE (provider credentials are sensitive, ADMIN+-gated
#     end to end), so there is no partial-permission gap to fix there.
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
        Permission.NOTIFICATION_READ,
        Permission.NOTIFICATION_WRITE,
    ]
)

_MEMBER_PERMS: frozenset[Permission] = frozenset(
    [
        Permission.ORG_READ,
        Permission.PROJECT_READ,
        Permission.PROJECT_WRITE,
        # PROJECT_DELETE: added in the EP-24 authorization audit. A MEMBER
        # who can create/rename a project must also be able to delete one —
        # withholding delete while granting write was an unintentional gap
        # (app/api/v1/projects.py's own docstring already claimed "MEMBER+
        # for write/delete", contradicted only by this omission).
        Permission.PROJECT_DELETE,
        Permission.PROVIDER_READ,
        Permission.USAGE_READ,
        Permission.API_KEY_READ,
        Permission.NOTIFICATION_READ,
        Permission.NOTIFICATION_WRITE,
    ]
)

_VIEWER_PERMS: frozenset[Permission] = frozenset(
    [
        Permission.ORG_READ,
        Permission.PROJECT_READ,
        Permission.PROVIDER_READ,
        Permission.USAGE_READ,
        Permission.API_KEY_READ,
        Permission.NOTIFICATION_READ,
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
