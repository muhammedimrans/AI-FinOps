"""Response schemas for the /v1/organizations endpoints (EP-12.1, EP-13)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class OrgMembershipItem(BaseModel):
    """One organization the authenticated user belongs to."""

    id: str  # organization UUID (hyphenated) — consumed directly by dashboard endpoints
    name: str
    slug: str
    role: str  # MembershipRole value: owner | admin | member | viewer
    # EP-22.2 Settings — Workspace section fields. Optional defaults keep
    # every pre-existing construction of this schema (list_my_organizations)
    # source-compatible without needing to be touched.
    description: str | None = None
    is_personal: bool = False
    created_at: datetime | None = None


class OrganizationsResponse(BaseModel):
    """List of organizations the authenticated user is a member of."""

    organizations: list[OrgMembershipItem]


class UpdateOrganizationRequest(BaseModel):
    """Update a workspace's editable fields (EP-21.3 onboarding Step 2, extended EP-22.2).

    ``name`` and ``description`` are independently optional — only fields
    present in the request are applied (``exclude_unset`` in the endpoint).
    The slug is never editable here — it is derived once at creation time
    (``AuthService.register`` / ``app.auth.slug.unique_slug``) and stays
    stable so existing links/references never break silently.
    """

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10000)


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
