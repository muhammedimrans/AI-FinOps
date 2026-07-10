"""Invitation accept/decline/resend/cancel API — EP-24.6.

These four endpoints are addressed by invitation *token* or *id*, never by
an ``org_id`` path parameter, so they live in their own router rather than
``app/api/v1/organizations.py`` — ``RequirePermission``/``RequireQueryPermission``
both require the org to be resolvable from the request itself, which isn't
true here. Endpoints:

  POST   /v1/invitations/{token}/accept  — join the org (CurrentUser required)
  POST   /v1/invitations/{token}/decline — decline, no auth required
  POST   /v1/invitations/{invitation_id}/resend — ADMIN/OWNER of the invitation's org
  DELETE /v1/invitations/{invitation_id}         — cancel, ADMIN/OWNER of the invitation's org

resend/cancel resolve the caller's membership manually (``ensure_org_membership``
+ ``has_permission``) since the org isn't known until the invitation row is
looked up — the same check ``RequirePermission`` performs internally, just
without a path-param org_id to hang a dependency off of.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.deps import DbDep, SettingsDep
from app.auth.dependencies import CurrentUser, ensure_org_membership
from app.auth.rbac import Permission, has_permission
from app.models.invitation import Invitation
from app.models.membership import Membership
from app.models.organization import Organization
from app.repositories.invitation_repository import InvitationRepository
from app.repositories.organization_repository import OrganizationRepository
from app.schemas.invitations import AcceptInvitationResponse, MessageResponse
from app.services.invitation_service import (
    InvalidInvitationTokenError,
    InvitationEmailMismatchError,
    InvitationService,
)

router = APIRouter(prefix="/invitations", tags=["invitations"])

_INVALID_TOKEN_DETAIL = "This invitation link is invalid or has expired."  # noqa: S105


@router.post(
    "/{token}/accept",
    response_model=AcceptInvitationResponse,
    summary="Accept an invitation",
    description=(
        "Requires an authenticated session — an unauthenticated caller "
        "should be redirected to log in/register first, then retry this "
        "call once authenticated (the frontend preserves the token across "
        "that redirect). The authenticated caller's email must match the "
        "invitation's."
    ),
)
async def accept_invitation(
    token: str,
    db: DbDep,
    settings: SettingsDep,
    current_user: CurrentUser,
) -> AcceptInvitationResponse:
    service = InvitationService(db, settings)
    try:
        membership = await service.accept_invitation(token=token, current_user=current_user)
    except InvitationEmailMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This invitation was sent to a different email address.",
        ) from exc
    except InvalidInvitationTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=_INVALID_TOKEN_DETAIL
        ) from exc

    org = await OrganizationRepository(db).get(membership.organization_id)
    org_name = org.name if org is not None else ""
    return AcceptInvitationResponse(
        organization_id=membership.organization_id,
        organization_name=org_name,
        role=membership.role.value,
    )


@router.post(
    "/{token}/decline",
    response_model=MessageResponse,
    summary="Decline an invitation",
    description="Public — no authentication required. No membership is ever created.",
)
async def decline_invitation(
    token: str,
    db: DbDep,
    settings: SettingsDep,
) -> MessageResponse:
    service = InvitationService(db, settings)
    try:
        await service.decline_invitation(token=token)
    except InvalidInvitationTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=_INVALID_TOKEN_DETAIL
        ) from exc
    return MessageResponse(message="Invitation declined.")


@router.post(
    "/{invitation_id}/resend",
    response_model=MessageResponse,
    summary="Resend an invitation",
    description="ADMIN/OWNER of the invitation's organization. Issues a new token and expiry.",
)
async def resend_invitation(
    invitation_id: uuid.UUID,
    db: DbDep,
    settings: SettingsDep,
    current_user: CurrentUser,
) -> MessageResponse:
    invitation, org, _membership = await _resolve_and_authorize(db, invitation_id, current_user)
    service = InvitationService(db, settings)
    await service.resend_invitation(invitation=invitation, organization=org, actor=current_user)
    return MessageResponse(message="Invitation resent.")


@router.delete(
    "/{invitation_id}",
    response_model=MessageResponse,
    summary="Cancel a pending invitation",
    description="ADMIN/OWNER of the invitation's organization. No membership is created.",
)
async def cancel_invitation(
    invitation_id: uuid.UUID,
    db: DbDep,
    settings: SettingsDep,
    current_user: CurrentUser,
) -> MessageResponse:
    invitation, org, _membership = await _resolve_and_authorize(db, invitation_id, current_user)
    service = InvitationService(db, settings)
    await service.cancel_invitation(invitation=invitation, organization=org, actor=current_user)
    return MessageResponse(message="Invitation cancelled.")


async def _resolve_and_authorize(
    db: DbDep, invitation_id: uuid.UUID, current_user: CurrentUser
) -> tuple[Invitation, Organization, Membership]:
    """Shared lookup for resend/cancel: resolve the invitation, its
    organization, and confirm the caller holds ORG_MANAGE_MEMBERS in that
    organization — the same check RequirePermission performs internally,
    applied manually since there's no org_id path param here."""
    inv_repo = InvitationRepository(db)
    invitation = await inv_repo.get(invitation_id)
    if invitation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")

    membership = await ensure_org_membership(
        db, user=current_user, org_id=invitation.organization_id
    )
    if not has_permission(membership.role, Permission.ORG_MANAGE_MEMBERS):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this action",
        )

    org = await OrganizationRepository(db).get(invitation.organization_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    return invitation, org, membership
