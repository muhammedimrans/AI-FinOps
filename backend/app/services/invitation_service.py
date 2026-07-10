"""InvitationService — organization team invitation lifecycle (EP-24.6).

Orchestrates create/accept/decline/resend for ``Invitation`` rows, reusing
the same primitives ``AuthService`` already established for its own
token-based flows (``app.auth.tokens.generate_refresh_token``/``hash_token``,
EP-05) and the existing ``EmailService`` for delivery (EP-24.4) — no second
token-generation or email-sending path is introduced. Accepting an
invitation creates a real ``Membership`` row via the existing
``MembershipRepository``, exactly as the pre-existing ``POST
/organizations/{id}/members`` shortcut does.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.tokens import generate_refresh_token, hash_token
from app.config.settings import Settings
from app.db.mixins import uuid7
from app.email.service import EmailService
from app.models.invitation import Invitation, InvitationStatus
from app.models.membership import Membership, MembershipRole
from app.models.organization import Organization
from app.models.user import User
from app.organizations.audit import OrgAuditEvent, log_org_event
from app.repositories.invitation_repository import InvitationRepository
from app.repositories.membership_repository import MembershipRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.user_repository import UserRepository

INVITATION_EXPIRY_DAYS = 7


class InvitationError(Exception):
    """Base class for invitation-flow errors the API layer maps to HTTP responses."""


class CannotInviteSelfError(InvitationError):
    """Raised when the caller invites their own email address."""


class AlreadyMemberError(InvitationError):
    """Raised when the target email already belongs to the organization."""


class DuplicatePendingInvitationError(InvitationError):
    """Raised when a still-pending, unexpired invitation already exists for this email."""


class InvalidInvitationTokenError(InvitationError):
    """Raised when a token doesn't resolve to a pending, unexpired invitation.

    Deliberately generic — never distinguishes "never existed" from
    "already used" from "expired" from "wrong token", per EP-24.6 Part 16's
    "do not leak information about invitations."
    """


class InvitationEmailMismatchError(InvitationError):
    """Raised when the authenticated caller's email doesn't match the invitation's."""


class InvitationNotFoundError(InvitationError):
    """Raised when an invitation id doesn't resolve to a row in the caller's organization."""


class PersonalOrganizationError(InvitationError):
    """Raised when an invitation is attempted against a personal (single-user) workspace.

    EP-25.1: a personal workspace's sole membership is fixed at creation
    (one OWNER, the account holder — see AuthService._create_workspace) and
    is never invitable, mirroring the existing is_personal guard on
    DELETE/PATCH /organizations/{id}.
    """


class InvitationService:
    """Orchestrates invitation creation, acceptance, decline, and resend."""

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        *,
        email_service: EmailService | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._repo = InvitationRepository(session)
        self._membership_repo = MembershipRepository(session)
        self._org_repo = OrganizationRepository(session)
        self._user_repo = UserRepository(session)
        # Optional-injection, matching AuthService/ProviderSyncService/
        # BudgetEvaluationService's established pattern elsewhere in this
        # codebase (EP-22/EP-24.2/EP-24.4).
        self._email = email_service or EmailService(settings)

    def _accept_url(self, raw_token: str) -> str:
        return f"{self._settings.dashboard_url}/accept-invite?token={raw_token}"

    # ── Create ────────────────────────────────────────────────────────────

    async def create_invitation(
        self,
        *,
        organization: Organization,
        email: str,
        role: MembershipRole,
        inviter: User,
    ) -> Invitation:
        if organization.is_personal:
            raise PersonalOrganizationError

        normalized_email = email.strip().lower()

        if normalized_email == inviter.email.strip().lower():
            raise CannotInviteSelfError

        existing_member = await self._membership_repo.get_by_org_and_email(
            organization.id, normalized_email
        )
        if existing_member is not None:
            raise AlreadyMemberError

        existing_invite = await self._repo.get_pending_by_org_and_email(
            organization.id, normalized_email
        )
        if existing_invite is not None:
            raise DuplicatePendingInvitationError

        raw_token = generate_refresh_token()
        now = datetime.now(UTC)

        invitation = Invitation()
        invitation.id = uuid7()
        invitation.organization_id = organization.id
        invitation.email = normalized_email
        invitation.role = role
        invitation.token_hash = hash_token(raw_token)
        invitation.status = InvitationStatus.PENDING
        invitation.created_by = inviter.id
        invitation.expires_at = now + timedelta(days=INVITATION_EXPIRY_DAYS)
        created = await self._repo.create(invitation)

        await self._email.send_invitation_email(
            to=normalized_email,
            organization_name=organization.name,
            inviter_name=inviter.display_name,
            role=role.value,
            accept_url=self._accept_url(raw_token),
            expires_at_display=created.expires_at.strftime("%B %d, %Y"),
        )
        log_org_event(
            OrgAuditEvent.INVITATION_SENT,
            organization_id=organization.id,
            actor_user_id=inviter.id,
            target_email=normalized_email,
            role=role.value,
        )
        return created

    # ── Resend ────────────────────────────────────────────────────────────

    async def resend_invitation(
        self,
        *,
        invitation: Invitation,
        organization: Organization,
        actor: User,
    ) -> Invitation:
        """Issue a new token + expiry on the same row, invalidating the
        previous one (overwriting ``token_hash`` means the old raw token —
        even if leaked — can never resolve to this row again)."""
        raw_token = generate_refresh_token()
        now = datetime.now(UTC)
        updated = await self._repo.update(
            invitation,
            token_hash=hash_token(raw_token),
            status=InvitationStatus.PENDING,
            expires_at=now + timedelta(days=INVITATION_EXPIRY_DAYS),
        )

        await self._email.send_invitation_email(
            to=updated.email,
            organization_name=organization.name,
            inviter_name=actor.display_name,
            role=updated.role.value,
            accept_url=self._accept_url(raw_token),
            expires_at_display=updated.expires_at.strftime("%B %d, %Y"),
        )
        log_org_event(
            OrgAuditEvent.INVITATION_RESENT,
            organization_id=organization.id,
            actor_user_id=actor.id,
            target_email=updated.email,
        )
        return updated

    # ── Accept ────────────────────────────────────────────────────────────

    async def accept_invitation(self, *, token: str, current_user: User) -> Membership:
        invitation = await self._repo.get_valid_by_token_hash(hash_token(token))
        if invitation is None:
            log_org_event(
                OrgAuditEvent.INVITATION_INVALID_TOKEN,
                actor_user_id=current_user.id,
            )
            raise InvalidInvitationTokenError

        if invitation.email.strip().lower() != current_user.email.strip().lower():
            raise InvitationEmailMismatchError

        org = await self._org_repo.get(invitation.organization_id)
        if org is None:
            raise InvalidInvitationTokenError

        membership = Membership()
        membership.id = uuid7()
        membership.organization_id = invitation.organization_id
        membership.user_id = current_user.id
        membership.user_email = current_user.email
        membership.role = invitation.role
        created_membership = await self._membership_repo.create(membership)

        now = datetime.now(UTC)
        await self._repo.update(
            invitation,
            status=InvitationStatus.ACCEPTED,
            accepted_by_user_id=current_user.id,
            accepted_at=now,
        )

        log_org_event(
            OrgAuditEvent.INVITATION_ACCEPTED,
            organization_id=invitation.organization_id,
            actor_user_id=current_user.id,
            target_email=invitation.email,
            role=invitation.role.value,
        )

        if invitation.created_by is not None:
            inviter = await self._user_repo.get(invitation.created_by)
            if inviter is not None:
                await self._email.send_invitation_accepted_email(
                    to=inviter.email,
                    organization_name=org.name,
                    member_email=current_user.email,
                    role=invitation.role.value,
                )

        return created_membership

    # ── Decline ───────────────────────────────────────────────────────────

    async def decline_invitation(self, *, token: str) -> Invitation:
        invitation = await self._repo.get_valid_by_token_hash(hash_token(token))
        if invitation is None:
            raise InvalidInvitationTokenError

        now = datetime.now(UTC)
        updated = await self._repo.update(
            invitation,
            status=InvitationStatus.CANCELLED,
            cancelled_at=now,
        )
        log_org_event(
            OrgAuditEvent.INVITATION_DECLINED,
            organization_id=invitation.organization_id,
            target_email=invitation.email,
        )
        return updated

    # ── Cancel (admin-initiated) ─────────────────────────────────────────

    async def cancel_invitation(
        self, *, invitation: Invitation, organization: Organization, actor: User
    ) -> Invitation:
        now = datetime.now(UTC)
        updated = await self._repo.update(
            invitation,
            status=InvitationStatus.CANCELLED,
            cancelled_at=now,
        )
        await self._email.send_invitation_cancelled_email(
            to=updated.email,
            organization_name=organization.name,
        )
        log_org_event(
            OrgAuditEvent.INVITATION_CANCELLED,
            organization_id=organization.id,
            actor_user_id=actor.id,
            target_email=updated.email,
        )
        return updated
