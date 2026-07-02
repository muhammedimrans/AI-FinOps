"""Response schemas for the /v1/organizations endpoints (EP-12.1, EP-13)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr


class OrgMembershipItem(BaseModel):
    """One organization the authenticated user belongs to."""

    id: str  # organization UUID (hyphenated) — consumed directly by dashboard endpoints
    name: str
    slug: str
    role: str  # MembershipRole value: owner | admin | member | viewer


class OrganizationsResponse(BaseModel):
    """List of organizations the authenticated user is a member of."""

    organizations: list[OrgMembershipItem]


# ── Member management (EP-13) ───────────────────────────────────────────────────


class MemberResponse(BaseModel):
    """One membership row within an organization."""

    id: uuid.UUID
    user_id: uuid.UUID | None
    email: str
    display_name: str | None
    role: str  # MembershipRole value
    # "active" — a User account is linked; "invited" — membership exists but
    # no account has been created/linked for this email yet.
    status: str
    created_at: datetime


class MembersListResponse(BaseModel):
    """All members of an organization."""

    members: list[MemberResponse]
    total: int


class InviteMemberRequest(BaseModel):
    """Add a member to an organization by email.

    This creates a membership row immediately; no email is sent (the platform
    has no outbound email transport yet — see the same limitation on password
    reset). If a User account with this email already exists, the membership
    is linked to it immediately and shows as "active". Otherwise it is
    "invited" and links automatically the first time that email signs in.
    """

    email: EmailStr
    role: str = "member"  # MembershipRole value


class UpdateMemberRoleRequest(BaseModel):
    """Change a member's role."""

    role: str  # MembershipRole value
