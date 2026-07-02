"""Organizations API — EP-12.1, EP-13.

Endpoints:
  GET    /v1/organizations                — orgs the current user belongs to
  GET    /v1/organizations/{org_id}/members                 — list members
  POST   /v1/organizations/{org_id}/members                 — add/invite a member
  PATCH  /v1/organizations/{org_id}/members/{membership_id} — change a member's role
  DELETE /v1/organizations/{org_id}/members/{membership_id} — remove a member

Authorization
--------------
Read (list) requires membership in the organization (any role). Write
operations (invite / change role / remove) require ORG_MANAGE_MEMBERS,
granted to ADMIN and OWNER. Only an existing OWNER may grant the OWNER role
to someone else — otherwise an ADMIN could invite a co-equal owner, a
privilege escalation. The organization's last remaining OWNER can never be
demoted or removed, to prevent an organization becoming ownerless.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import and_

from app.api.deps import DbDep
from app.auth.dependencies import CurrentMembership, CurrentUser, RequirePermission
from app.auth.rbac import Permission
from app.db.mixins import uuid7
from app.models.membership import Membership, MembershipRole
from app.models.user import User
from app.repositories.membership_repository import MembershipRepository
from app.repositories.user_repository import UserRepository
from app.schemas.organizations import (
    InviteMemberRequest,
    MemberResponse,
    MembersListResponse,
    OrganizationsResponse,
    OrgMembershipItem,
    UpdateMemberRoleRequest,
)

router = APIRouter(prefix="/organizations", tags=["organizations"])


def _parse_role(value: str) -> MembershipRole:
    try:
        return MembershipRole(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid role {value!r}. Must be one of: {[r.value for r in MembershipRole]}",
        ) from exc


def _to_member_response(m: Membership, user: User | None) -> MemberResponse:
    return MemberResponse(
        id=m.id,
        user_id=m.user_id,
        email=m.user_email,
        display_name=user.display_name if user else None,
        role=m.role.value,
        status="active" if m.user_id is not None else "invited",
        created_at=m.created_at,
    )


async def _count_owners(repo: MembershipRepository, org_id: uuid.UUID) -> int:
    return await repo.count(
        extra_filters=and_(
            Membership.organization_id == org_id,
            Membership.role == MembershipRole.OWNER,
        )
    )


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


@router.get(
    "/{org_id}/members",
    response_model=MembersListResponse,
    summary="List organization members",
    description=(
        "Returns every member of the organization, including pending invitations "
        "(status='invited' — no User account is linked yet)."
    ),
)
async def list_members(
    org_id: uuid.UUID,
    db: DbDep,
    _member: CurrentMembership,
) -> MembersListResponse:
    repo = MembershipRepository(db)
    memberships = await repo.list_by_org_with_users(org_id)
    items = [_to_member_response(m, m.user) for m in memberships]
    return MembersListResponse(members=items, total=len(items))


@router.post(
    "/{org_id}/members",
    response_model=MemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add or invite a member",
    description=(
        "Creates a membership for the given email. If a User account with that "
        "email already exists, the membership is linked immediately (status="
        "'active'). Otherwise it is created unlinked (status='invited') and "
        "links automatically the first time that email signs in. No email is "
        "sent — the platform has no outbound email transport yet."
    ),
)
async def invite_member(
    org_id: uuid.UUID,
    body: InviteMemberRequest,
    db: DbDep,
    caller: Annotated[Membership, RequirePermission(Permission.ORG_MANAGE_MEMBERS)],
) -> MemberResponse:
    role = _parse_role(body.role)
    if role == MembershipRole.OWNER and caller.role != MembershipRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only an organization owner can grant the owner role",
        )

    repo = MembershipRepository(db)
    existing = await repo.get_by_org_and_email(org_id, body.email)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This email is already a member of the organization",
        )

    existing_user = await UserRepository(db).get_by_email(body.email)

    membership = Membership()
    membership.id = uuid7()
    membership.organization_id = org_id
    membership.user_email = body.email
    membership.user_id = existing_user.id if existing_user else None
    membership.role = role
    created = await repo.create(membership)

    return _to_member_response(created, existing_user)


@router.patch(
    "/{org_id}/members/{membership_id}",
    response_model=MemberResponse,
    summary="Change a member's role",
)
async def update_member_role(
    org_id: uuid.UUID,
    membership_id: uuid.UUID,
    body: UpdateMemberRoleRequest,
    db: DbDep,
    caller: Annotated[Membership, RequirePermission(Permission.ORG_MANAGE_MEMBERS)],
) -> MemberResponse:
    new_role = _parse_role(body.role)
    if new_role == MembershipRole.OWNER and caller.role != MembershipRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only an organization owner can grant the owner role",
        )

    repo = MembershipRepository(db)
    target = await repo.get(membership_id)
    if target is None or target.organization_id != org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    if target.role == MembershipRole.OWNER and new_role != MembershipRole.OWNER:
        if await _count_owners(repo, org_id) <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot change the role of the organization's only owner",
            )

    updated = await repo.update(target, role=new_role)
    user = await UserRepository(db).get(updated.user_id) if updated.user_id else None
    return _to_member_response(updated, user)


@router.delete(
    "/{org_id}/members/{membership_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a member",
)
async def remove_member(
    org_id: uuid.UUID,
    membership_id: uuid.UUID,
    db: DbDep,
    _caller: Annotated[Membership, RequirePermission(Permission.ORG_MANAGE_MEMBERS)],
) -> None:
    repo = MembershipRepository(db)
    target = await repo.get(membership_id)
    if target is None or target.organization_id != org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    if target.role == MembershipRole.OWNER and await _count_owners(repo, org_id) <= 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot remove the organization's only owner",
        )

    await repo.soft_delete(target)
