"""Response schemas for the /v1/organizations endpoint (EP-12.1)."""

from __future__ import annotations

from pydantic import BaseModel


class OrgMembershipItem(BaseModel):
    """One organization the authenticated user belongs to."""

    id: str  # org external_id — "org_<hex>"
    name: str
    slug: str
    role: str  # MembershipRole value: owner | admin | member | viewer


class OrganizationsResponse(BaseModel):
    """List of organizations the authenticated user is a member of."""

    organizations: list[OrgMembershipItem]
