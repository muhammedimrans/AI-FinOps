"""Response schemas for the /v1/rbac endpoints (EP-13)."""

from __future__ import annotations

from pydantic import BaseModel


class RoleInfo(BaseModel):
    """A membership role and the permissions it grants."""

    role: str  # MembershipRole value: owner | admin | member | viewer
    label: str  # human-readable display name
    permissions: list[str]  # Permission values, e.g. "org:read"


class RolesResponse(BaseModel):
    """Every role in the system and its permission set."""

    roles: list[RoleInfo]


class PermissionInfo(BaseModel):
    """A single permission, grouped by domain for display."""

    permission: str  # e.g. "org:read"
    domain: str  # e.g. "org"
    action: str  # e.g. "read"


class PermissionsResponse(BaseModel):
    """Every permission defined in the system."""

    permissions: list[PermissionInfo]
