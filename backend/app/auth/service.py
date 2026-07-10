"""AuthService — authentication business logic (EP-05 / F-017 through F-019)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.audit import AuditEvent, log_auth_event
from app.auth.exceptions import (
    AccountDisabledError,
    EmailAlreadyRegisteredError,
    EmailAlreadyVerifiedError,
    InvalidCredentialsError,
    InvalidTokenError,
    OwnerOfSharedWorkspaceError,
    UsernameAlreadyTakenError,
)
from app.auth.password import hash_password, verify_password
from app.auth.slug import unique_slug
from app.auth.tokens import (
    create_access_token,
    generate_refresh_token,
    hash_token,
)
from app.config.settings import Settings
from app.db.mixins import uuid7
from app.email.service import EmailService
from app.models.membership import Membership, MembershipRole
from app.models.organization import Organization, OrganizationStatus
from app.models.password_reset_token import PasswordResetToken
from app.models.session import Session
from app.models.user import User, UserStatus
from app.models.verification_token import VerificationToken
from app.repositories.membership_repository import MembershipRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.password_reset_token_repository import PasswordResetTokenRepository
from app.repositories.session_repository import SessionRepository
from app.repositories.user_repository import UserRepository
from app.repositories.verification_token_repository import VerificationTokenRepository


class TokenPair:
    """Holds an access+refresh token pair and expiry metadata."""

    __slots__ = ("access_token", "expires_in", "refresh_token", "token_type")

    def __init__(
        self,
        *,
        access_token: str,
        refresh_token: str,
        token_type: str = "bearer",  # noqa: S107
        expires_in: int,
    ) -> None:
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.token_type = token_type
        self.expires_in = expires_in


class AuthService:
    """Orchestrates login, logout, token refresh, email verification, and password reset."""

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        *,
        email_service: EmailService | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._user_repo = UserRepository(session)
        self._session_repo = SessionRepository(session)
        self._verify_repo = VerificationTokenRepository(session)
        self._reset_repo = PasswordResetTokenRepository(session)
        self._membership_repo = MembershipRepository(session)
        self._org_repo = OrganizationRepository(session)
        # Optional-injection, matching ProviderSyncService/BudgetEvaluationService's
        # established pattern elsewhere in this codebase (EP-22/EP-24.2) — every
        # real call site needs nothing more than the default; tests substitute a
        # fake EmailService without any DI container changes.
        self._email = email_service or EmailService(settings)

    # ── Shared session issuance ──────────────────────────────────────────────

    async def _issue_session(
        self,
        user: User,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> TokenPair:
        """Create a DB-backed session row + signed access token for `user`.

        Shared by `login()` and `register()` — every code path that starts
        an authenticated browser session goes through this one place.
        """
        refresh_raw = generate_refresh_token()
        refresh_hash = hash_token(refresh_raw)
        expire_delta = timedelta(days=self._settings.jwt_refresh_token_expire_days)
        expires_at = datetime.now(UTC) + expire_delta

        db_session = Session()
        db_session.id = uuid7()
        db_session.user_id = user.id
        db_session.refresh_token_hash = refresh_hash
        db_session.expires_at = expires_at
        db_session.ip_address = ip_address
        db_session.user_agent = user_agent
        await self._session_repo.create(db_session)

        access = create_access_token(
            user_id=str(user.id),
            session_id=str(db_session.id),
            email=user.email,
            settings=self._settings,
        )
        return TokenPair(
            access_token=access,
            refresh_token=refresh_raw,
            expires_in=self._settings.jwt_access_token_expire_minutes * 60,
        )

    # ── Registration ──────────────────────────────────────────────────────────

    async def register(
        self,
        *,
        email: str,
        password: str,
        display_name: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[TokenPair, User, Organization]:
        """
        Create a User, a personal workspace (Organization, is_personal=True),
        and an OWNER Membership linking them, then issue a session — all in
        one transaction. Mirrors the User+Organization+Membership pattern
        already used by `app/db/seed.py::seed_demo_data`, extended with the
        is_personal flag and wired to real request-time input instead of
        hardcoded seed constants.

        The account is created ACTIVE (not gated on email verification) —
        requiring a delivered, clicked verification email before a brand
        new user can even see their own workspace would be a needless
        activation-funnel drop-off; `email_verified` starts False and a
        verification email is sent below (EP-24.4), but nothing in the
        product blocks on it being clicked.
        """
        if await self._user_repo.email_exists(email):
            raise EmailAlreadyRegisteredError

        user = User()
        user.id = uuid7()
        user.email = email
        user.display_name = display_name
        user.status = UserStatus.ACTIVE
        user.email_verified = False
        user.password_hash = hash_password(password)
        await self._user_repo.create(user)

        org = Organization()
        org.id = uuid7()
        org.name = f"{display_name}'s Workspace"
        org.slug = await unique_slug(
            f"{display_name}-workspace", slug_exists=self._org_repo.slug_exists
        )
        org.is_personal = True
        org.status = OrganizationStatus.ACTIVE
        await self._org_repo.create(org)

        membership = Membership()
        membership.id = uuid7()
        membership.organization_id = org.id
        membership.user_id = user.id
        membership.user_email = user.email
        membership.role = MembershipRole.OWNER
        await self._membership_repo.create(membership)

        pair = await self._issue_session(user, ip_address=ip_address, user_agent=user_agent)
        await self._user_repo.update_last_login(user.id)

        log_auth_event(
            AuditEvent.REGISTRATION, user_id=user.id, email=user.email, ip_address=ip_address
        )
        await self._send_verification_email(user)

        return pair, user, org

    # ── Login ─────────────────────────────────────────────────────────────────

    async def login(
        self,
        *,
        email: str,
        password: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[TokenPair, User]:
        """Authenticate credentials and create a new session."""
        user = await self._user_repo.get_by_email(email)
        if user is None or user.password_hash is None:
            raise InvalidCredentialsError
        if not verify_password(user.password_hash, password):
            raise InvalidCredentialsError
        if user.status == UserStatus.DISABLED:
            raise AccountDisabledError

        # Activate any organization invitations created before this account
        # existed (invite-by-email creates a Membership with user_id=None).
        await self._membership_repo.link_pending_by_email(user.email, user.id)

        pair = await self._issue_session(user, ip_address=ip_address, user_agent=user_agent)
        await self._user_repo.update_last_login(user.id)
        return pair, user

    # ── Logout ────────────────────────────────────────────────────────────────

    async def logout(self, *, session_id: uuid.UUID) -> None:
        """Revoke the session, invalidating the associated refresh token."""
        await self._session_repo.revoke(session_id)

    # ── Onboarding (EP-21.3) ─────────────────────────────────────────────────

    async def complete_onboarding(self, *, user: User) -> User:
        """
        Mark the first-time onboarding wizard as completed for this user.

        Idempotent: calling this more than once simply refreshes the
        timestamp rather than erroring, since the frontend's "Finish" step
        is the only caller and there is no scenario where re-completing is
        invalid. ``user`` is the session-bound instance from CurrentUser, so
        this mutates it directly and flushes — same pattern as
        ``verify_email``/``reset_password`` above.
        """
        user.onboarding_completed_at = datetime.now(UTC)
        await self._session.flush()
        return user

    # ── Profile / preferences (EP-22.2 Settings) ─────────────────────────────

    async def update_profile(
        self,
        *,
        user: User,
        display_name: str | None = None,
        username: str | None = None,
        avatar_url: str | None = None,
        bio: str | None = None,
        timezone: str | None = None,
        set_fields: set[str] | None = None,
    ) -> User:
        """
        Apply a partial profile update. ``set_fields`` names exactly which of
        the keyword args were actually supplied by the caller (the endpoint
        passes ``body.model_fields_set``) so an omitted field is left
        untouched rather than overwritten with ``None``.
        """
        fields = set_fields or set()
        if "username" in fields and username:
            if await self._user_repo.username_exists(username, exclude_id=user.id):
                raise UsernameAlreadyTakenError
        if "display_name" in fields and display_name is not None:
            user.display_name = display_name
        if "username" in fields:
            user.username = username
        if "avatar_url" in fields:
            user.avatar_url = avatar_url
        if "bio" in fields:
            user.bio = bio
        if "timezone" in fields:
            user.timezone = timezone
        await self._session.flush()
        return user

    async def update_preferences(self, *, user: User, patch: dict[str, Any]) -> User:
        """Shallow-merge ``patch`` into ``user.preferences``."""
        merged = {**user.preferences, **patch}
        user.preferences = merged
        await self._session.flush()
        return user

    # ── Password change (EP-22.2) ────────────────────────────────────────────

    async def change_password(
        self,
        *,
        user: User,
        current_password: str,
        new_password: str,
        current_session_id: uuid.UUID,
    ) -> None:
        """
        Verify the caller's current password, set the new one, and revoke
        every other active session (matching ``reset_password``'s
        "sign out everywhere" behavior) while keeping the session that made
        this request alive.
        """
        if user.password_hash is None or not verify_password(user.password_hash, current_password):
            raise InvalidCredentialsError
        user.password_hash = hash_password(new_password)
        await self._session.flush()
        await self._session_repo.revoke_all_for_user_except(user.id, current_session_id)
        log_auth_event(AuditEvent.PASSWORD_CHANGED, user_id=user.id, email=user.email)

    # ── Account deletion (EP-22.2 Settings — Danger Zone) ────────────────────

    async def delete_account(self, *, user: User, password: str) -> None:
        """
        Verify the caller's password, then permanently (soft-)delete the
        account and every workspace they solely own.

        Refuses (``OwnerOfSharedWorkspaceError``) when the user is OWNER of
        a workspace that still has other members — deleting the account
        would otherwise silently orphan that workspace. The caller must
        transfer ownership or remove the other members first. Workspaces
        the user owns alone (including their personal workspace) are
        soft-deleted along with the account; memberships where the user
        holds a non-OWNER role are left as-is (soft-deleting the user is
        enough to end their access).
        """
        if user.password_hash is None or not verify_password(user.password_hash, password):
            raise InvalidCredentialsError

        memberships = await self._membership_repo.list_by_user_email_with_orgs(user.email)
        owned = [m for m in memberships if m.role == MembershipRole.OWNER]
        for m in owned:
            other_members = await self._membership_repo.list_by_org_with_users(m.organization_id)
            if any(x.user_email != user.email for x in other_members):
                raise OwnerOfSharedWorkspaceError(m.organization.name)

        for m in owned:
            org = await self._org_repo.get(m.organization_id)
            if org is not None:
                await self._org_repo.soft_delete(org, deleted_by=user.id)

        await self._user_repo.soft_delete(user, deleted_by=user.id)
        await self._session_repo.revoke_all_for_user(user.id)

    # ── Refresh ───────────────────────────────────────────────────────────────

    async def refresh(self, *, refresh_token: str) -> TokenPair:
        """
        Rotate the refresh token and issue a new access token.

        The old refresh token is invalidated immediately (hash replaced),
        preventing replay attacks even if the token is intercepted in transit.
        """
        token_hash = hash_token(refresh_token)
        db_session = await self._session_repo.get_active_by_token_hash(token_hash)
        if db_session is None:
            raise InvalidTokenError("Refresh token is invalid, expired, or revoked")

        user = await self._user_repo.get(db_session.user_id)
        if user is None or user.status == UserStatus.DISABLED:
            raise InvalidTokenError("Associated user is inactive or not found")

        new_refresh_raw = generate_refresh_token()
        new_refresh_hash = hash_token(new_refresh_raw)
        new_expires_at = datetime.now(UTC) + timedelta(
            days=self._settings.jwt_refresh_token_expire_days
        )
        await self._session_repo.rotate(
            db_session.id,
            new_token_hash=new_refresh_hash,
            new_expires_at=new_expires_at,
        )

        access = create_access_token(
            user_id=str(user.id),
            session_id=str(db_session.id),
            email=user.email,
            settings=self._settings,
        )
        return TokenPair(
            access_token=access,
            refresh_token=new_refresh_raw,
            expires_in=self._settings.jwt_access_token_expire_minutes * 60,
        )

    # ── Email verification (EP-05 tokens, EP-24.4 delivery) ─────────────────────

    def _frontend_url(self, path: str, *, token: str) -> str:
        """Build a dashboard URL (the app that owns /verify-email and
        /reset-password, EP-05) carrying the raw token as a query param —
        the same shape those pages already read via ``useSearchParams``."""
        base = self._settings.dashboard_url.rstrip("/")
        return f"{base}{path}?token={token}"

    async def create_verification_token(self, *, user_id: uuid.UUID) -> str:
        """Create and persist an email verification token; return the raw token.

        Invalidates every previously-issued, still-valid token for this user
        first (EP-24.4 replay protection) — mirrors
        ``create_password_reset_token``'s existing behavior for the same
        reason: only the newest outstanding link should ever be redeemable.
        """
        await self._verify_repo.invalidate_for_user(user_id)

        raw = generate_refresh_token()
        token_hash = hash_token(raw)
        expires_at = datetime.now(UTC) + timedelta(hours=24)

        vt = VerificationToken()
        vt.id = uuid7()
        vt.user_id = user_id
        vt.token_hash = token_hash
        vt.expires_at = expires_at
        await self._verify_repo.create(vt)
        return raw

    async def _send_verification_email(self, user: User) -> None:
        raw = await self.create_verification_token(user_id=user.id)
        verify_url = self._frontend_url("/verify-email", token=raw)
        await self._email.send_verification_email(
            to=user.email,
            display_name=user.display_name,
            verify_url=verify_url,
        )
        log_auth_event(AuditEvent.VERIFICATION_EMAIL_SENT, user_id=user.id, email=user.email)

    async def resend_verification_email(self, *, email: str) -> None:
        """
        Re-send the verification email for ``email``, if that account
        exists and isn't already verified.

        Deliberately silent (no return value, never raises for "not
        found"/"already verified") — the endpoint returns the same generic
        response regardless of outcome, exactly like
        ``create_password_reset_token``'s existing anti-enumeration
        contract, so a caller can't use this endpoint to probe which
        emails have an account.
        """
        user = await self._user_repo.get_by_email(email)
        if user is None or user.email_verified:
            return
        await self._send_verification_email(user)

    async def verify_email(self, *, token: str) -> User:
        """Consume a verification token and mark the user's email as verified."""
        token_hash = hash_token(token)
        vt = await self._verify_repo.get_valid_by_hash(token_hash)
        if vt is None:
            log_auth_event(AuditEvent.VERIFICATION_FAILURE, reason="invalid_or_expired_token")
            raise InvalidTokenError("Verification token is invalid, expired, or already used")

        user = await self._user_repo.get(vt.user_id)
        if user is None:
            log_auth_event(
                AuditEvent.VERIFICATION_FAILURE, user_id=vt.user_id, reason="user_not_found"
            )
            raise InvalidTokenError("User associated with this token no longer exists")
        if user.email_verified:
            raise EmailAlreadyVerifiedError

        await self._verify_repo.mark_used(vt.id)
        if user.status == UserStatus.INVITED:
            user.status = UserStatus.ACTIVE
        user.email_verified = True
        await self._session.flush()

        log_auth_event(AuditEvent.VERIFICATION_SUCCESS, user_id=user.id, email=user.email)
        await self._email.send_welcome_email(to=user.email, display_name=user.display_name)
        return user

    # ── Password reset ────────────────────────────────────────────────────────

    async def create_password_reset_token(self, *, email: str) -> str | None:
        """
        Create a password-reset token for the given email, and send the
        reset email (EP-24.4).

        Returns the raw token when the user exists, or None when not found
        (callers should NOT reveal which outcome occurred to the requester —
        the endpoint returns the same response either way).
        """
        user = await self._user_repo.get_by_email(email)
        log_auth_event(AuditEvent.PASSWORD_RESET_REQUESTED, email=email)
        if user is None:
            return None

        await self._reset_repo.invalidate_for_user(user.id)

        raw = generate_refresh_token()
        token_hash = hash_token(raw)
        expires_at = datetime.now(UTC) + timedelta(hours=1)

        prt = PasswordResetToken()
        prt.id = uuid7()
        prt.user_id = user.id
        prt.token_hash = token_hash
        prt.expires_at = expires_at
        await self._reset_repo.create(prt)

        reset_url = self._frontend_url("/reset-password", token=raw)
        await self._email.send_password_reset_email(
            to=user.email,
            display_name=user.display_name,
            reset_url=reset_url,
        )
        return raw

    async def reset_password(self, *, token: str, new_password: str) -> None:
        """Consume a reset token and update the user's password hash."""
        token_hash = hash_token(token)
        prt = await self._reset_repo.get_valid_by_hash(token_hash)
        if prt is None:
            raise InvalidTokenError("Reset token is invalid, expired, or already used")

        user = await self._user_repo.get(prt.user_id)
        if user is None:
            raise InvalidTokenError("User associated with this token no longer exists")

        await self._reset_repo.mark_used(prt.id)
        user.password_hash = hash_password(new_password)
        await self._session.flush()

        await self._session_repo.revoke_all_for_user(user.id)
        log_auth_event(AuditEvent.PASSWORD_RESET_COMPLETED, user_id=user.id, email=user.email)
