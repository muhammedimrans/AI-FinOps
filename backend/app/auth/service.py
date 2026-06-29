"""AuthService — authentication business logic (EP-05 / F-017 through F-019)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.exceptions import (
    AccountDisabledError,
    EmailAlreadyVerifiedError,
    InvalidCredentialsError,
    InvalidTokenError,
)
from app.auth.password import hash_password, verify_password
from app.auth.tokens import (
    create_access_token,
    generate_refresh_token,
    hash_token,
)
from app.config.settings import Settings
from app.db.mixins import uuid7
from app.models.password_reset_token import PasswordResetToken
from app.models.session import Session
from app.models.user import User, UserStatus
from app.models.verification_token import VerificationToken
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

    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._user_repo = UserRepository(session)
        self._session_repo = SessionRepository(session)
        self._verify_repo = VerificationTokenRepository(session)
        self._reset_repo = PasswordResetTokenRepository(session)

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
        pair = TokenPair(
            access_token=access,
            refresh_token=refresh_raw,
            expires_in=self._settings.jwt_access_token_expire_minutes * 60,
        )

        await self._user_repo.update_last_login(user.id)
        return pair, user

    # ── Logout ────────────────────────────────────────────────────────────────

    async def logout(self, *, session_id: uuid.UUID) -> None:
        """Revoke the session, invalidating the associated refresh token."""
        await self._session_repo.revoke(session_id)

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

    # ── Email verification ────────────────────────────────────────────────────

    async def create_verification_token(self, *, user_id: uuid.UUID) -> str:
        """Create and persist an email verification token; return the raw token."""
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

    async def verify_email(self, *, token: str) -> User:
        """Consume a verification token and mark the user's email as verified."""
        token_hash = hash_token(token)
        vt = await self._verify_repo.get_valid_by_hash(token_hash)
        if vt is None:
            raise InvalidTokenError("Verification token is invalid, expired, or already used")

        user = await self._user_repo.get(vt.user_id)
        if user is None:
            raise InvalidTokenError("User associated with this token no longer exists")
        if user.email_verified:
            raise EmailAlreadyVerifiedError

        await self._verify_repo.mark_used(vt.id)
        if user.status == UserStatus.INVITED:
            user.status = UserStatus.ACTIVE
        user.email_verified = True
        await self._session.flush()
        return user

    # ── Password reset ────────────────────────────────────────────────────────

    async def create_password_reset_token(self, *, email: str) -> str | None:
        """
        Create a password-reset token for the given email.

        Returns the raw token when the user exists, or None when not found
        (callers should NOT reveal which outcome occurred to the requester).
        """
        user = await self._user_repo.get_by_email(email)
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
