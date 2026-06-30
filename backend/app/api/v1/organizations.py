"""Organizations API — EP-12.1.

Endpoints:
  GET /v1/organizations  — list organizations the current user belongs to
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import DbDep
from app.auth.dependencies import CurrentUser
from app.repositories.membership_repository import MembershipRepository
from app.schemas.organizations import OrganizationsResponse, OrgMembershipItem

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.get(
    "/",
    response_model=OrganizationsResponse,
    summary="List organizations the authenticated user belongs to",
)
async def list_my_organizations(
    current_user: CurrentUser,
    db: DbDep,
) -> OrganizationsResponse:
    repo = MembershipRepository(db)
    memberships = await repo.list_by_user_email_with_orgs(current_user.email)
    return OrganizationsResponse(
        organizations=[
            OrgMembershipItem(
                id=str(m.organization.id),
                name=m.organization.name,
                slug=m.organization.slug,
                role=m.role.value,
            )
            for m in memberships
        ]
    )
