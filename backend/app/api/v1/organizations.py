"""Organizations API — EP-12.1, EP-13, EP-14, EP-15, EP-21.3, EP-24.6.

Endpoints:
  GET    /v1/organizations                — orgs the current user belongs to
  PATCH  /v1/organizations/{org_id}       — update name/description of a workspace
  DELETE /v1/organizations/{org_id}       — delete a workspace (EP-22.2, not personal)
  GET    /v1/organizations/{org_id}/members                 — list members
  POST   /v1/organizations/{org_id}/members                 — add/invite a member (immediate, EP-13)
  PATCH  /v1/organizations/{org_id}/members/{membership_id} — change a member's role
  DELETE /v1/organizations/{org_id}/members/{membership_id} — remove a member
  GET    /v1/organizations/{org_id}/invitations              — list pending invitations
  POST   /v1/organizations/{org_id}/invitations              — send a real, email-token invite
  POST   /v1/organizations/{org_id}/transfer-ownership        — hand OWNER to another member
  GET    /v1/organizations/{org_id}/api-keys                — list API keys
  POST   /v1/organizations/{org_id}/api-keys                — create an API key
  PATCH  /v1/organizations/{org_id}/api-keys/{key_id}        — rename an API key (EP-22.2)
  DELETE /v1/organizations/{org_id}/api-keys/{key_id}        — revoke an API key

Token-based invitation accept/decline/resend/cancel live in
``app/api/v1/invitations.py`` instead — they're addressed by invitation
token or id, not by ``org_id`` path parameter, so they can't use this
router's ``RequirePermission`` (which requires an ``org_id`` path segment).

Authorization
--------------
Members: read (list) requires membership in the organization (any role).
Write operations (invite / change role / remove) require ORG_MANAGE_MEMBERS,
granted to ADMIN and OWNER. Only an existing OWNER may grant the OWNER role
to someone else — otherwise an ADMIN could invite a co-equal owner, a
privilege escalation. The organization's last remaining OWNER can never be
demoted or removed, to prevent an organization becoming ownerless.
EP-24.6 adds two further restrictions RequirePermission alone can't
express: an OWNER can never demote *themselves* (transfer ownership is the
correct path — see ``ORG_TRANSFER_OWNERSHIP`` below), and an ADMIN can
never remove an OWNER even when other owners exist.

Invitations (EP-24.6): create/list/cancel/resend require ORG_MANAGE_MEMBERS
(same as the pre-existing member-management endpoints — inviting a real
person is the same privilege level as directly adding one). Transferring
ownership requires the new, OWNER-only ``ORG_TRANSFER_OWNERSHIP``
permission — never granted to ADMIN, mirroring ``ORG_DELETE``'s precedent
that an organization's most irreversible actions require its most senior
role.

API keys (EP-14): read requires API_KEY_READ (every role); create/revoke
require API_KEY_WRITE, granted only to ADMIN and OWNER. The raw key is
generated in the service layer and returned exactly once, in the POST
response — it is never persisted or retrievable again.

EP-15: GET .../api-keys additionally accepts an Organization API Key
(`Authorization: Bearer costorah_live_...`) in place of a JWT session, via
RequireMembershipOrApiKeyPermission (app/auth/api_key_auth.py) — the first
endpoint wired to the new API key authentication flow. POST/DELETE remain
JWT-only; a key cannot mint or revoke other keys in this phase.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.dedup import api_key_scope, membership_scope
from app.alerts.dispatcher import AlertService
from app.api.deps import DbDep, EventBusDep, SettingsDep
from app.auth.api_key_auth import RequireMembershipOrApiKeyPermission
from app.auth.dependencies import CurrentMembership, CurrentUser, RequirePermission
from app.auth.rate_limit import EmailRateLimiter
from app.auth.rbac import Permission
from app.db.mixins import uuid7
from app.models.alert import AlertSeverity, AlertType
from app.models.invitation import Invitation, InvitationStatus
from app.models.membership import Membership, MembershipRole
from app.models.organization_api_key import OrganizationApiKey
from app.models.user import User
from app.organizations.audit import OrgAuditEvent, log_org_event
from app.realtime.event_bus import EventBus
from app.repositories.invitation_repository import InvitationRepository
from app.repositories.membership_repository import MembershipRepository
from app.repositories.organization_api_key_repository import OrganizationApiKeyRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.user_repository import UserRepository
from app.schemas.invitations import (
    CreateInvitationRequest,
    InvitationResponse,
    InvitationsListResponse,
    TransferOwnershipRequest,
)
from app.schemas.organization_api_keys import (
    ApiKeyCreatedResponse,
    ApiKeyResponse,
    ApiKeysListResponse,
    CreateApiKeyRequest,
    UpdateApiKeyRequest,
)
from app.schemas.organizations import (
    InviteMemberRequest,
    MemberResponse,
    MembersListResponse,
    OrganizationsResponse,
    OrgMembershipItem,
    UpdateMemberRoleRequest,
    UpdateOrganizationRequest,
)
from app.services.api_key_auth_service import ApiKeyAuthContext
from app.services.invitation_service import (
    AlreadyMemberError,
    CannotInviteSelfError,
    DuplicatePendingInvitationError,
    InvitationService,
)
from app.services.organization_api_key_service import (
    InvalidPermissionError,
    OrganizationApiKeyService,
)

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/organizations", tags=["organizations"])


async def _fire_alert_safely(
    db: AsyncSession,
    event_bus: EventBus,
    *,
    organization_id: uuid.UUID,
    alert_type: AlertType,
    severity: AlertSeverity,
    title: str,
    message: str,
    source: str,
    scope: str,
    metadata: dict[str, Any],
) -> None:
    """EP-19.3 — fires a membership/API-key lifecycle alert. Errors here are
    logged and swallowed, never raised: an alerting bug must never fail the
    membership or API-key mutation that triggered it (matching the same
    never-block-the-primary-flow discipline used in app/api/v1/ingest.py's
    `_check_budget_alerts`)."""
    try:
        await AlertService(db, event_bus).fire(
            organization_id=organization_id,
            alert_type=alert_type,
            severity=severity,
            title=title,
            message=message,
            source=source,
            scope=scope,
            metadata=metadata,
        )
    except Exception:
        log.warning(
            "alert_fire_failed",
            organization_id=str(organization_id),
            alert_type=alert_type.value,
            exc_info=True,
        )


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


def _to_invitation_response(inv: Invitation, creator: User | None = None) -> InvitationResponse:
    # "expired" is never persisted (see Invitation model's own docstring) —
    # derived here, the one place every reader of this response sees it.
    effective_status = inv.status.value
    if inv.status == InvitationStatus.PENDING and inv.expires_at <= datetime.now(UTC):
        effective_status = "expired"
    return InvitationResponse(
        id=inv.id,
        organization_id=inv.organization_id,
        email=inv.email,
        role=inv.role.value,
        status=effective_status,
        invited_by_name=creator.display_name if creator else None,
        invited_by_email=creator.email if creator else None,
        created_at=inv.created_at,
        expires_at=inv.expires_at,
        accepted_at=inv.accepted_at,
        cancelled_at=inv.cancelled_at,
    )


def _get_invitation_rate_limiter(request: Request) -> EmailRateLimiter:
    """App-wide invitation-send rate limiter — same lazily-created,
    app.state-cached, Redis-backed pattern as auth.py's
    ``_get_email_rate_limiter`` (EP-24.4), a distinct instance because the
    scope key (org_id:email, not just email) and call sites differ."""
    limiter = getattr(request.app.state, "invitation_rate_limiter", None)
    if limiter is None:
        container = getattr(request.app.state, "container", None)
        limiter = EmailRateLimiter(redis=getattr(container, "redis", None))
        request.app.state.invitation_rate_limiter = limiter
    return limiter


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
                description=m.organization.description,
                is_personal=m.organization.is_personal,
                created_at=m.organization.created_at,
            )
            for m in memberships
        ]
    )


@router.patch(
    "/{org_id}",
    response_model=OrgMembershipItem,
    summary="Update a workspace's name and/or description",
    description=(
        "EP-21.3 onboarding Step 2, extended EP-22.2 Settings — updates the "
        "workspace's display name and/or description. Only fields present "
        "in the request are applied. The slug is not editable here and "
        "never changes as a side effect."
    ),
)
async def update_organization(
    org_id: uuid.UUID,
    body: UpdateOrganizationRequest,
    db: DbDep,
    caller: Annotated[Membership, RequirePermission(Permission.ORG_WRITE)],
) -> OrgMembershipItem:
    repo = OrganizationRepository(db)
    org = await repo.get(org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    changes = body.model_dump(exclude_unset=True)
    updated = await repo.update(org, **changes) if changes else org
    return OrgMembershipItem(
        id=str(updated.id),
        name=updated.name,
        slug=updated.slug,
        role=caller.role.value,
        description=updated.description,
        is_personal=updated.is_personal,
        created_at=updated.created_at,
    )


@router.delete(
    "/{org_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a workspace",
    description=(
        "EP-22.2 Settings — Danger Zone. Requires ORG_DELETE (OWNER only). "
        "Refuses to delete the caller's personal workspace, which every "
        "account requires — see AuthService.register."
    ),
)
async def delete_organization(
    org_id: uuid.UUID,
    db: DbDep,
    _caller: Annotated[Membership, RequirePermission(Permission.ORG_DELETE)],
) -> None:
    repo = OrganizationRepository(db)
    org = await repo.get(org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    if org.is_personal:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your personal workspace cannot be deleted.",
        )
    await repo.soft_delete(org)


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
    event_bus: EventBusDep,
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

    await _fire_alert_safely(
        db,
        event_bus,
        organization_id=org_id,
        alert_type=AlertType.ORG_MEMBER_ADDED,
        severity=AlertSeverity.INFO,
        title=f"{body.email} joined the organization",
        message=f"{body.email} was added as {role.value}.",
        source="membership",
        scope=membership_scope(org_id, body.email),
        metadata={"email": body.email, "role": role.value},
    )

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
        # EP-24.6: an OWNER can never demote themselves, even if other
        # owners exist — transfer ownership (POST .../transfer-ownership)
        # is the only sanctioned way to hand off the role, so this can
        # never leave a workspace with zero owners as a side effect of an
        # accidental self-demotion.
        if target.id == caller.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Owners cannot demote themselves — transfer ownership instead",
            )
        if await _count_owners(repo, org_id) <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot change the role of the organization's only owner",
            )

    old_role = target.role
    updated = await repo.update(target, role=new_role)
    user = await UserRepository(db).get(updated.user_id) if updated.user_id else None
    log_org_event(
        OrgAuditEvent.MEMBER_ROLE_CHANGED,
        organization_id=org_id,
        actor_user_id=caller.user_id,
        target_email=updated.user_email,
        old_role=old_role.value,
        new_role=new_role.value,
    )
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
    event_bus: EventBusDep,
    caller: Annotated[Membership, RequirePermission(Permission.ORG_MANAGE_MEMBERS)],
) -> None:
    repo = MembershipRepository(db)
    target = await repo.get(membership_id)
    if target is None or target.organization_id != org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    if target.role == MembershipRole.OWNER:
        # EP-24.6: an ADMIN can never remove an OWNER, regardless of how
        # many owners exist — only an OWNER may remove another OWNER.
        if caller.role != MembershipRole.OWNER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only an owner can remove another owner",
            )
        if await _count_owners(repo, org_id) <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot remove the organization's only owner",
            )

    removed_email, removed_role = target.user_email, target.role
    await repo.soft_delete(target)

    log_org_event(
        OrgAuditEvent.MEMBER_REMOVED,
        organization_id=org_id,
        actor_user_id=caller.user_id,
        target_email=removed_email,
        role=removed_role.value,
    )
    await _fire_alert_safely(
        db,
        event_bus,
        organization_id=org_id,
        alert_type=AlertType.ORG_MEMBER_REMOVED,
        severity=AlertSeverity.INFO,
        title=f"{removed_email} was removed from the organization",
        message=f"{removed_email} ({removed_role.value}) was removed from the organization.",
        source="membership",
        scope=membership_scope(org_id, removed_email),
        metadata={"email": removed_email, "role": removed_role.value},
    )


# ═══════════════════════════════════════════════════════════════════════════
# Invitations (EP-24.6) — the real, email-token invite flow. Token-addressed
# accept/decline/resend/cancel live in app/api/v1/invitations.py instead.
# ═══════════════════════════════════════════════════════════════════════════


@router.get(
    "/{org_id}/invitations",
    response_model=InvitationsListResponse,
    summary="List pending invitations",
)
async def list_invitations(
    org_id: uuid.UUID,
    db: DbDep,
    _caller: Annotated[Membership, RequirePermission(Permission.ORG_MANAGE_MEMBERS)],
) -> InvitationsListResponse:
    repo = InvitationRepository(db)
    invitations = await repo.list_pending_by_org(org_id)
    items = [_to_invitation_response(inv, inv.creator) for inv in invitations]
    return InvitationsListResponse(invitations=items, total=len(items))


@router.post(
    "/{org_id}/invitations",
    response_model=InvitationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Invite a teammate by email",
    description=(
        "Sends a real invitation email containing a one-time accept link. "
        "Nothing is granted until the invitee actively accepts — unlike "
        "POST /members, which creates a membership immediately."
    ),
)
async def create_invitation(
    org_id: uuid.UUID,
    body: CreateInvitationRequest,
    request: Request,
    db: DbDep,
    settings: SettingsDep,
    current_user: CurrentUser,
    caller: Annotated[Membership, RequirePermission(Permission.ORG_MANAGE_MEMBERS)],
) -> InvitationResponse:
    role = _parse_role(body.role)
    if role == MembershipRole.OWNER and caller.role != MembershipRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only an organization owner can grant the owner role",
        )

    normalized_email = body.email.strip().lower()
    limiter = _get_invitation_rate_limiter(request)
    decision = await limiter.check_and_record(
        scope="invitation", key=f"{org_id}:{normalized_email}"
    )
    if not decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many invitations sent to this address. Please wait before retrying.",
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )

    org = await OrganizationRepository(db).get(org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    service = InvitationService(db, settings)
    try:
        created = await service.create_invitation(
            organization=org, email=body.email, role=role, inviter=current_user
        )
    except CannotInviteSelfError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="You cannot invite yourself",
        ) from exc
    except AlreadyMemberError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This email is already a member of the organization",
        ) from exc
    except DuplicatePendingInvitationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This email already has a pending invitation",
        ) from exc

    return _to_invitation_response(created, current_user)


@router.post(
    "/{org_id}/transfer-ownership",
    response_model=MemberResponse,
    summary="Transfer organization ownership to another member",
    description=(
        "OWNER only. The caller's own membership becomes ADMIN and the "
        "target member's becomes OWNER, in one transaction — an "
        "organization is never briefly ownerless."
    ),
)
async def transfer_ownership(
    org_id: uuid.UUID,
    body: TransferOwnershipRequest,
    db: DbDep,
    caller: Annotated[Membership, RequirePermission(Permission.ORG_TRANSFER_OWNERSHIP)],
) -> MemberResponse:
    repo = MembershipRepository(db)
    new_owner = await repo.get(body.new_owner_membership_id)
    if new_owner is None or new_owner.organization_id != org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    if new_owner.id == caller.id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="You are already the owner",
        )

    await repo.update(new_owner, role=MembershipRole.OWNER)
    await repo.update(caller, role=MembershipRole.ADMIN)

    log_org_event(
        OrgAuditEvent.OWNERSHIP_TRANSFERRED,
        organization_id=org_id,
        actor_user_id=caller.user_id,
        target_email=new_owner.user_email,
    )

    user = await UserRepository(db).get(new_owner.user_id) if new_owner.user_id else None
    return _to_member_response(new_owner, user)


# ═══════════════════════════════════════════════════════════════════════════
# API keys (EP-14 Phase 1)
# ═══════════════════════════════════════════════════════════════════════════


def _to_api_key_response(key: OrganizationApiKey) -> ApiKeyResponse:
    return ApiKeyResponse(
        id=key.id,
        name=key.name,
        description=key.description,
        prefix=key.key_prefix,
        permissions=key.permissions,
        created_at=key.created_at,
        expires_at=key.expires_at,
        last_used_at=key.last_used_at,
    )


@router.get(
    "/{org_id}/api-keys",
    response_model=ApiKeysListResponse,
    summary="List organization API keys",
    description=(
        "Returns every non-revoked API key for the organization. Never "
        "includes the key hash or the raw key — only the display prefix.\n\n"
        "Accepts either a dashboard session (JWT) or an "
        "`Authorization: Bearer costorah_live_...` Organization API Key "
        "(EP-15) with the `api_key:read` scope — the first endpoint wired "
        "to the new API key authentication flow, establishing the pattern "
        "for future machine-to-machine endpoints."
    ),
    openapi_extra={"security": [{"OAuth2PasswordBearer": []}, {"ApiKeyAuth": []}]},
)
async def list_api_keys(
    org_id: uuid.UUID,
    db: DbDep,
    _auth: Annotated[
        Membership | ApiKeyAuthContext,
        RequireMembershipOrApiKeyPermission(Permission.API_KEY_READ),
    ],
) -> ApiKeysListResponse:
    repo = OrganizationApiKeyRepository(db)
    keys = await repo.list(org_id)
    items = [_to_api_key_response(k) for k in keys]
    return ApiKeysListResponse(keys=items, total=len(items))


@router.post(
    "/{org_id}/api-keys",
    response_model=ApiKeyCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an API key",
    description=(
        "Generates a new key and returns the full raw secret exactly once, "
        "in this response. It cannot be retrieved again — only its prefix "
        "and metadata are available afterward via GET."
    ),
)
async def create_api_key(
    org_id: uuid.UUID,
    body: CreateApiKeyRequest,
    db: DbDep,
    event_bus: EventBusDep,
    current_user: CurrentUser,
    _caller: Annotated[Membership, RequirePermission(Permission.API_KEY_WRITE)],
) -> ApiKeyCreatedResponse:
    service = OrganizationApiKeyService(db)
    try:
        record, raw_key = await service.create_key(
            organization_id=org_id,
            name=body.name,
            description=body.description,
            permissions=body.permissions,
            expiration=body.expiration,
            created_by=current_user.id,
        )
    except InvalidPermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unrecognized permission scope: {exc}",
        ) from exc

    # Never include raw_key here — the raw secret is returned exactly once,
    # in the response below, and must never be persisted, logged, or stored
    # in alert metadata.
    await _fire_alert_safely(
        db,
        event_bus,
        organization_id=org_id,
        alert_type=AlertType.API_KEY_CREATED,
        severity=AlertSeverity.INFO,
        title=f"API key '{record.name}' created",
        message=f"A new API key '{record.name}' ({record.key_prefix}...) was created.",
        source="api_key",
        scope=api_key_scope(record.id),
        metadata={"api_key_id": str(record.id), "name": record.name, "prefix": record.key_prefix},
    )

    return ApiKeyCreatedResponse(
        id=record.id,
        api_key=raw_key,
        prefix=record.key_prefix,
        name=record.name,
        permissions=record.permissions,
        created_at=record.created_at,
        expires_at=record.expires_at,
    )


@router.patch(
    "/{org_id}/api-keys/{key_id}",
    response_model=ApiKeyResponse,
    summary="Rename an API key",
    description=(
        "EP-22.2 Settings — API Keys section. Updates name/description "
        "only; only fields present in the request are applied. Permissions, "
        "expiration, and the key material are immutable after creation."
    ),
)
async def update_api_key(
    org_id: uuid.UUID,
    key_id: uuid.UUID,
    body: UpdateApiKeyRequest,
    db: DbDep,
    _caller: Annotated[Membership, RequirePermission(Permission.API_KEY_WRITE)],
) -> ApiKeyResponse:
    repo = OrganizationApiKeyRepository(db)
    target = await repo.get(key_id)
    if target is None or target.organization_id != org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")

    changes = body.model_dump(exclude_unset=True)
    updated = await repo.update(target, **changes) if changes else target
    return _to_api_key_response(updated)


@router.delete(
    "/{org_id}/api-keys/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke an API key",
)
async def delete_api_key(
    org_id: uuid.UUID,
    key_id: uuid.UUID,
    db: DbDep,
    event_bus: EventBusDep,
    current_user: CurrentUser,
    _caller: Annotated[Membership, RequirePermission(Permission.API_KEY_WRITE)],
) -> None:
    repo = OrganizationApiKeyRepository(db)
    target = await repo.get(key_id)
    if target is None or target.organization_id != org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")

    service = OrganizationApiKeyService(db)
    await service.delete_key(target, deleted_by=current_user.id)

    await _fire_alert_safely(
        db,
        event_bus,
        organization_id=org_id,
        alert_type=AlertType.API_KEY_REVOKED,
        severity=AlertSeverity.MEDIUM,
        title=f"API key '{target.name}' revoked",
        message=f"API key '{target.name}' ({target.key_prefix}...) was revoked.",
        source="api_key",
        scope=api_key_scope(target.id),
        metadata={"api_key_id": str(target.id), "name": target.name, "prefix": target.key_prefix},
    )
