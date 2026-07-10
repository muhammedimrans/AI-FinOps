"""
Tests for EP-05 — Authentication and RBAC Foundation (F-017 through F-022).

Covers (without a live database):
  - Argon2id password hashing / verification (F-018)
  - JWT access-token creation, decoding, and expiry (F-017)
  - Refresh-token generation and SHA-256 hashing utilities (F-017)
  - RBAC permission model: role → permission mapping (F-021)
  - Auth exception hierarchy (F-017)
  - Auth request/response schemas (F-017)
  - AuthService method signatures via mocked repositories (F-017-F-019)
  - get_current_user dependency: JWT validation paths (F-022)
  - Auth API endpoints: login, logout, refresh, verify-email,
    request-password-reset, reset-password (F-017)
  - Model instantiation: Session, VerificationToken, PasswordResetToken (F-020)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.auth.exceptions import (
    AccountDisabledError,
    AuthError,
    EmailAlreadyVerifiedError,
    InvalidCredentialsError,
    InvalidTokenError,
)
from app.auth.password import hash_password, needs_rehash, verify_password
from app.auth.rbac import (
    ROLE_PERMISSIONS,
    Permission,
    get_permissions,
    has_permission,
)
from app.auth.tokens import (
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_token,
)
from app.config.settings import Settings
from app.db.mixins import uuid7
from app.models.membership import MembershipRole
from app.models.password_reset_token import PasswordResetToken
from app.models.session import Session
from app.models.user import UserStatus
from app.models.verification_token import VerificationToken
from app.schemas.auth import (
    LoginRequest,
    MessageResponse,
    PasswordResetRequest,
    RefreshRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserPublic,
    VerifyEmailRequest,
)
from tests.conftest import make_user

# ─── Helpers ──────────────────────────────────────────────────────────────────

_TEST_SECRET = "test-jwt-secret-for-unit-tests-only!!"
_TEST_PASSWORD = "correct-horse-battery-staple"


def _test_settings() -> Settings:
    return Settings(
        app_env="testing",
        app_secret_key="test-secret-key-with-at-least-32-chars!!",
        jwt_secret=_TEST_SECRET,
    )


def _make_session(
    *,
    user_id: uuid.UUID | None = None,
    expires_in_seconds: int = 3600,
    revoked: bool = False,
) -> Session:
    obj = Session()
    obj.id = uuid7()
    obj.user_id = user_id or uuid7()
    obj.refresh_token_hash = "a" * 64
    obj.expires_at = datetime.now(UTC) + timedelta(seconds=expires_in_seconds)
    obj.revoked_at = datetime.now(UTC) if revoked else None
    return obj


# ─── F-018: Argon2id password hashing ────────────────────────────────────────


class TestPasswordHashing:
    def test_hash_returns_argon2_string(self) -> None:
        hashed = hash_password(_TEST_PASSWORD)
        assert hashed.startswith("$argon2id$")

    def test_verify_correct_password(self) -> None:
        hashed = hash_password(_TEST_PASSWORD)
        assert verify_password(hashed, _TEST_PASSWORD) is True

    def test_verify_wrong_password(self) -> None:
        hashed = hash_password(_TEST_PASSWORD)
        assert verify_password(hashed, "wrong-password") is False

    def test_verify_empty_password(self) -> None:
        hashed = hash_password(_TEST_PASSWORD)
        assert verify_password(hashed, "") is False

    def test_each_hash_is_unique(self) -> None:
        h1 = hash_password(_TEST_PASSWORD)
        h2 = hash_password(_TEST_PASSWORD)
        assert h1 != h2

    def test_needs_rehash_fresh(self) -> None:
        hashed = hash_password(_TEST_PASSWORD)
        assert needs_rehash(hashed) is False

    def test_verify_invalid_hash_returns_false(self) -> None:
        assert verify_password("not-a-valid-hash", _TEST_PASSWORD) is False

    def test_hash_not_empty(self) -> None:
        assert len(hash_password("x")) > 20


# ─── F-017: JWT tokens ────────────────────────────────────────────────────────


class TestJWTTokens:
    def setup_method(self) -> None:
        self.settings = _test_settings()

    def test_create_access_token_returns_string(self) -> None:
        token = create_access_token(
            user_id=str(uuid.uuid4()),
            session_id=str(uuid.uuid4()),
            email="test@example.com",
            settings=self.settings,
        )
        assert isinstance(token, str)
        assert len(token) > 20

    def test_decode_access_token_valid(self) -> None:
        uid = str(uuid.uuid4())
        sid = str(uuid.uuid4())
        token = create_access_token(
            user_id=uid,
            session_id=sid,
            email="test@example.com",
            settings=self.settings,
        )
        claims = decode_access_token(token, settings=self.settings)
        assert claims["sub"] == uid
        assert claims["jti"] == sid
        assert claims["email"] == "test@example.com"
        assert claims["type"] == "access"

    def test_decode_wrong_secret_raises(self) -> None:
        token = create_access_token(
            user_id="uid",
            session_id="sid",
            email="x@x.com",
            settings=self.settings,
        )
        bad_settings = Settings(
            app_env="testing",
            app_secret_key="test-secret-key-with-at-least-32-chars!!",
            jwt_secret="completely-different-secret-key-abc",
        )
        from jwt.exceptions import DecodeError

        with pytest.raises(DecodeError):
            decode_access_token(token, settings=bad_settings)

    def test_decode_expired_token_raises(self) -> None:
        import time

        import jwt

        now = int(time.time()) - 120
        payload = {
            "sub": "uid",
            "jti": "sid",
            "email": "x@x.com",
            "iat": now,
            "exp": now - 1,  # 2 minutes past — beyond the 30s clock-skew leeway
            "type": "access",
        }
        token = jwt.encode(payload, _TEST_SECRET, algorithm="HS256")
        from jwt.exceptions import ExpiredSignatureError

        with pytest.raises(ExpiredSignatureError):
            decode_access_token(token, settings=self.settings)

    def test_decode_wrong_type_raises(self) -> None:
        import jwt

        payload = {
            "sub": "uid",
            "jti": "sid",
            "email": "x@x.com",
            "iat": int(datetime.now(UTC).timestamp()),
            "exp": int((datetime.now(UTC) + timedelta(minutes=5)).timestamp()),
            "type": "refresh",
        }
        token = jwt.encode(payload, _TEST_SECRET, algorithm="HS256")
        from jwt.exceptions import InvalidTokenError

        with pytest.raises(InvalidTokenError):
            decode_access_token(token, settings=self.settings)

    def test_decode_garbage_raises(self) -> None:
        from jwt.exceptions import DecodeError

        with pytest.raises(DecodeError):
            decode_access_token("not.a.jwt", settings=self.settings)

    def test_generate_refresh_token_is_string(self) -> None:
        rt = generate_refresh_token()
        assert isinstance(rt, str)
        assert len(rt) >= 40

    def test_generate_refresh_tokens_are_unique(self) -> None:
        tokens = {generate_refresh_token() for _ in range(50)}
        assert len(tokens) == 50

    def test_hash_token_is_sha256(self) -> None:
        raw = "some-raw-token"
        digest = hash_token(raw)
        assert len(digest) == 64
        assert all(c in "0123456789abcdef" for c in digest)

    def test_hash_token_deterministic(self) -> None:
        raw = "same-input"
        assert hash_token(raw) == hash_token(raw)

    def test_hash_token_different_inputs(self) -> None:
        assert hash_token("a") != hash_token("b")


# ─── F-021: RBAC permission model ────────────────────────────────────────────


class TestRBACPermissions:
    def test_owner_has_all_permissions(self) -> None:
        for perm in Permission:
            assert has_permission(MembershipRole.OWNER, perm)

    def test_viewer_has_org_read(self) -> None:
        assert has_permission(MembershipRole.VIEWER, Permission.ORG_READ)

    def test_viewer_cannot_write_org(self) -> None:
        assert not has_permission(MembershipRole.VIEWER, Permission.ORG_WRITE)

    def test_viewer_cannot_delete_project(self) -> None:
        assert not has_permission(MembershipRole.VIEWER, Permission.PROJECT_DELETE)

    def test_member_can_write_project(self) -> None:
        assert has_permission(MembershipRole.MEMBER, Permission.PROJECT_WRITE)

    def test_member_cannot_manage_members(self) -> None:
        assert not has_permission(MembershipRole.MEMBER, Permission.ORG_MANAGE_MEMBERS)

    def test_admin_can_manage_members(self) -> None:
        assert has_permission(MembershipRole.ADMIN, Permission.ORG_MANAGE_MEMBERS)

    def test_admin_cannot_delete_org(self) -> None:
        assert not has_permission(MembershipRole.ADMIN, Permission.ORG_DELETE)

    def test_owner_can_delete_org(self) -> None:
        assert has_permission(MembershipRole.OWNER, Permission.ORG_DELETE)

    def test_admin_can_read_billing(self) -> None:
        assert has_permission(MembershipRole.ADMIN, Permission.BILLING_READ)

    def test_admin_cannot_write_billing(self) -> None:
        assert not has_permission(MembershipRole.ADMIN, Permission.BILLING_WRITE)

    def test_owner_can_write_billing(self) -> None:
        assert has_permission(MembershipRole.OWNER, Permission.BILLING_WRITE)

    def test_get_permissions_owner_is_all(self) -> None:
        owner_perms = get_permissions(MembershipRole.OWNER)
        assert owner_perms == frozenset(Permission)

    def test_get_permissions_viewer_subset_of_member(self) -> None:
        viewer = get_permissions(MembershipRole.VIEWER)
        member = get_permissions(MembershipRole.MEMBER)
        assert viewer.issubset(member)

    def test_role_permissions_coverage(self) -> None:
        assert set(ROLE_PERMISSIONS.keys()) == set(MembershipRole)

    def test_permission_strings_format(self) -> None:
        for perm in Permission:
            assert ":" in perm


# ─── F-017: Auth exceptions ───────────────────────────────────────────────────


class TestAuthExceptions:
    def test_invalid_credentials_is_auth_error(self) -> None:
        assert issubclass(InvalidCredentialsError, AuthError)

    def test_account_disabled_is_auth_error(self) -> None:
        assert issubclass(AccountDisabledError, AuthError)

    def test_invalid_token_is_auth_error(self) -> None:
        assert issubclass(InvalidTokenError, AuthError)

    def test_email_already_verified_is_auth_error(self) -> None:
        assert issubclass(EmailAlreadyVerifiedError, AuthError)

    def test_raise_and_catch_invalid_credentials(self) -> None:
        with pytest.raises(InvalidCredentialsError):
            raise InvalidCredentialsError

    def test_raise_and_catch_via_base(self) -> None:
        with pytest.raises(AuthError):
            raise AccountDisabledError


# ─── F-017: Auth schemas ──────────────────────────────────────────────────────


class TestAuthSchemas:
    def test_login_request_valid(self) -> None:
        req = LoginRequest(email="user@example.com", password="secret")
        assert req.email == "user@example.com"
        assert req.password == "secret"

    def test_login_request_invalid_email(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            LoginRequest(email="not-an-email", password="secret")

    def test_login_request_empty_password(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            LoginRequest(email="user@example.com", password="")

    def test_refresh_request_valid(self) -> None:
        req = RefreshRequest(refresh_token="some-token")
        assert req.refresh_token == "some-token"

    def test_verify_email_request_valid(self) -> None:
        req = VerifyEmailRequest(token="abc123")
        assert req.token == "abc123"

    def test_password_reset_request_valid(self) -> None:
        req = PasswordResetRequest(email="user@example.com")
        assert req.email == "user@example.com"

    def test_reset_password_request_valid(self) -> None:
        req = ResetPasswordRequest(token="tok", new_password="newpassword123")
        assert req.new_password == "newpassword123"

    def test_reset_password_too_short(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ResetPasswordRequest(token="tok", new_password="short")

    def test_token_response_default_type(self) -> None:
        resp = TokenResponse(access_token="a", refresh_token="r", expires_in=1800)
        assert resp.token_type == "bearer"

    def test_user_public_from_dict(self) -> None:
        from datetime import UTC, datetime

        up = UserPublic(
            id="usr_abc",
            email="x@x.com",
            username=None,
            display_name="X",
            status="active",
            email_verified=True,
            onboarding_completed=False,
            avatar_url=None,
            bio=None,
            timezone=None,
            created_at=datetime.now(UTC),
            preferences={},
            google_linked=False,
            google_email=None,
            last_login_provider=None,
        )
        assert up.email_verified is True

    def test_message_response(self) -> None:
        mr = MessageResponse(message="OK")
        assert mr.message == "OK"


# ─── F-020: Session model ─────────────────────────────────────────────────────


class TestSessionModel:
    def test_session_instantiation(self) -> None:
        s = _make_session()
        assert s.id is not None
        assert s.refresh_token_hash == "a" * 64

    def test_is_revoked_false(self) -> None:
        s = _make_session()
        assert s.is_revoked is False

    def test_is_revoked_true(self) -> None:
        s = _make_session(revoked=True)
        assert s.is_revoked is True

    def test_external_id_prefix(self) -> None:
        s = _make_session()
        assert s.external_id.startswith("ses_")

    def test_tablename(self) -> None:
        assert Session.__tablename__ == "sessions"


# ─── F-019: VerificationToken model ──────────────────────────────────────────


class TestVerificationTokenModel:
    def test_verification_token_instantiation(self) -> None:
        vt = VerificationToken()
        vt.id = uuid7()
        vt.user_id = uuid7()
        vt.token_hash = "b" * 64
        vt.expires_at = datetime.now(UTC) + timedelta(hours=24)
        assert vt.id is not None

    def test_external_id_prefix(self) -> None:
        vt = VerificationToken()
        vt.id = uuid7()
        assert vt.external_id.startswith("vt_")

    def test_tablename(self) -> None:
        assert VerificationToken.__tablename__ == "verification_tokens"


# ─── F-018: PasswordResetToken model ─────────────────────────────────────────


class TestPasswordResetTokenModel:
    def test_password_reset_token_instantiation(self) -> None:
        prt = PasswordResetToken()
        prt.id = uuid7()
        prt.user_id = uuid7()
        prt.token_hash = "c" * 64
        prt.expires_at = datetime.now(UTC) + timedelta(hours=1)
        assert prt.id is not None

    def test_external_id_prefix(self) -> None:
        prt = PasswordResetToken()
        prt.id = uuid7()
        assert prt.external_id.startswith("pr_")

    def test_tablename(self) -> None:
        assert PasswordResetToken.__tablename__ == "password_reset_tokens"


# ─── AuthService (mocked) ─────────────────────────────────────────────────────


class TestAuthServiceLogin:
    def setup_method(self) -> None:
        self.settings = _test_settings()
        self.mock_session = AsyncMock()
        self.user = make_user(password_hash=hash_password(_TEST_PASSWORD))

    def _make_svc(self) -> Any:
        from app.auth.service import AuthService

        svc = AuthService(self.mock_session, self.settings)
        svc._user_repo = AsyncMock()
        svc._session_repo = AsyncMock()
        svc._verify_repo = AsyncMock()
        svc._reset_repo = AsyncMock()
        svc._membership_repo = AsyncMock()
        return svc

    @pytest.mark.asyncio
    async def test_login_returns_token_pair_and_user(self) -> None:
        svc = self._make_svc()
        svc._user_repo.get_by_email.return_value = self.user
        svc._session_repo.create = AsyncMock(return_value=None)
        svc._user_repo.update_last_login = AsyncMock()

        pair, user = await svc.login(email=self.user.email, password=_TEST_PASSWORD)
        assert pair.access_token
        assert pair.refresh_token
        assert user is self.user

    @pytest.mark.asyncio
    async def test_login_wrong_password_raises(self) -> None:
        svc = self._make_svc()
        svc._user_repo.get_by_email.return_value = self.user

        with pytest.raises(InvalidCredentialsError):
            await svc.login(email=self.user.email, password="wrong!")

    @pytest.mark.asyncio
    async def test_login_user_not_found_raises(self) -> None:
        svc = self._make_svc()
        svc._user_repo.get_by_email.return_value = None

        with pytest.raises(InvalidCredentialsError):
            await svc.login(email="missing@example.com", password=_TEST_PASSWORD)

    @pytest.mark.asyncio
    async def test_login_disabled_user_raises(self) -> None:
        svc = self._make_svc()
        disabled = make_user(
            status=UserStatus.DISABLED,
            password_hash=hash_password(_TEST_PASSWORD),
        )
        svc._user_repo.get_by_email.return_value = disabled

        with pytest.raises(AccountDisabledError):
            await svc.login(email=disabled.email, password=_TEST_PASSWORD)

    @pytest.mark.asyncio
    async def test_login_no_password_hash_raises(self) -> None:
        svc = self._make_svc()
        no_pw = make_user(password_hash=None)
        svc._user_repo.get_by_email.return_value = no_pw

        with pytest.raises(InvalidCredentialsError):
            await svc.login(email=no_pw.email, password=_TEST_PASSWORD)


class TestAuthServiceRegister:
    """EP-21.2: self-serve registration + personal-workspace auto-creation."""

    def setup_method(self) -> None:
        self.settings = _test_settings()
        self.mock_session = AsyncMock()

    def _make_svc(self) -> Any:
        from app.auth.service import AuthService

        svc = AuthService(self.mock_session, self.settings)
        svc._user_repo = AsyncMock()
        svc._session_repo = AsyncMock()
        svc._verify_repo = AsyncMock()
        svc._reset_repo = AsyncMock()
        svc._membership_repo = AsyncMock()
        svc._org_repo = AsyncMock()
        return svc

    @pytest.mark.asyncio
    async def test_register_creates_user_org_and_owner_membership(self) -> None:
        from app.models.membership import MembershipRole

        svc = self._make_svc()
        svc._user_repo.email_exists.return_value = False
        svc._org_repo.slug_exists.return_value = False

        pair, user, workspace = await svc.register(
            email="new@example.com",
            password=_TEST_PASSWORD,
            display_name="New User",
        )

        assert pair.access_token
        assert pair.refresh_token
        assert user.email == "new@example.com"
        assert user.status == UserStatus.ACTIVE
        assert user.email_verified is False
        assert workspace.is_personal is True
        assert workspace.name == "New User's Workspace"
        assert workspace.slug == "new-user-workspace"

        svc._user_repo.create.assert_awaited_once()
        svc._org_repo.create.assert_awaited_once()
        membership_arg = svc._membership_repo.create.call_args[0][0]
        assert membership_arg.role == MembershipRole.OWNER
        assert membership_arg.organization_id == workspace.id
        assert membership_arg.user_id == user.id
        svc._session_repo.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_register_duplicate_email_raises(self) -> None:
        from app.auth.exceptions import EmailAlreadyRegisteredError

        svc = self._make_svc()
        svc._user_repo.email_exists.return_value = True

        with pytest.raises(EmailAlreadyRegisteredError):
            await svc.register(
                email="taken@example.com",
                password=_TEST_PASSWORD,
                display_name="Someone",
            )
        svc._user_repo.create.assert_not_awaited()
        svc._org_repo.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_register_slug_collision_appends_suffix(self) -> None:
        svc = self._make_svc()
        svc._user_repo.email_exists.return_value = False
        # First candidate taken, second free.
        svc._org_repo.slug_exists.side_effect = [True, False]

        _, _, workspace = await svc.register(
            email="dup@example.com",
            password=_TEST_PASSWORD,
            display_name="Dup Name",
        )
        assert workspace.slug == "dup-name-workspace-2"

    @pytest.mark.asyncio
    async def test_register_hashes_password_not_stored_in_plaintext(self) -> None:
        svc = self._make_svc()
        svc._user_repo.email_exists.return_value = False
        svc._org_repo.slug_exists.return_value = False

        _, user, _ = await svc.register(
            email="secure@example.com",
            password=_TEST_PASSWORD,
            display_name="Secure",
        )
        assert user.password_hash != _TEST_PASSWORD
        assert verify_password(user.password_hash, _TEST_PASSWORD) is True


class TestAuthServiceLogout:
    def setup_method(self) -> None:
        self.settings = _test_settings()
        self.mock_session = AsyncMock()

    def _make_svc(self) -> Any:
        from app.auth.service import AuthService

        svc = AuthService(self.mock_session, self.settings)
        svc._session_repo = AsyncMock()
        return svc

    @pytest.mark.asyncio
    async def test_logout_calls_revoke(self) -> None:
        svc = self._make_svc()
        sid = uuid.uuid4()
        await svc.logout(session_id=sid)
        svc._session_repo.revoke.assert_called_once_with(sid)


class TestAuthServiceRefresh:
    def setup_method(self) -> None:
        self.settings = _test_settings()
        self.mock_session = AsyncMock()
        self.user = make_user()

    def _make_svc(self) -> Any:
        from app.auth.service import AuthService

        svc = AuthService(self.mock_session, self.settings)
        svc._user_repo = AsyncMock()
        svc._session_repo = AsyncMock()
        return svc

    @pytest.mark.asyncio
    async def test_refresh_invalid_token_raises(self) -> None:
        svc = self._make_svc()
        svc._session_repo.get_active_by_token_hash.return_value = None

        with pytest.raises(InvalidTokenError):
            await svc.refresh(refresh_token="bad-token")

    @pytest.mark.asyncio
    async def test_refresh_valid_returns_new_pair(self) -> None:
        svc = self._make_svc()
        db_session = _make_session(user_id=self.user.id)
        svc._session_repo.get_active_by_token_hash.return_value = db_session
        svc._user_repo.get.return_value = self.user
        svc._session_repo.rotate = AsyncMock()

        pair = await svc.refresh(refresh_token="valid-raw-refresh")
        assert pair.access_token
        assert pair.refresh_token
        svc._session_repo.rotate.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_disabled_user_raises(self) -> None:
        svc = self._make_svc()
        db_session = _make_session()
        svc._session_repo.get_active_by_token_hash.return_value = db_session
        svc._user_repo.get.return_value = make_user(status=UserStatus.DISABLED)

        with pytest.raises(InvalidTokenError):
            await svc.refresh(refresh_token="some-token")


class TestAuthServiceEmailVerification:
    def setup_method(self) -> None:
        self.settings = _test_settings()
        self.mock_session = AsyncMock()
        self.user = make_user(status=UserStatus.INVITED, email_verified=False)

    def _make_svc(self) -> Any:
        from app.auth.service import AuthService

        svc = AuthService(self.mock_session, self.settings)
        svc._user_repo = AsyncMock()
        svc._verify_repo = AsyncMock()
        return svc

    @pytest.mark.asyncio
    async def test_verify_email_invalid_token_raises(self) -> None:
        svc = self._make_svc()
        svc._verify_repo.get_valid_by_hash.return_value = None

        with pytest.raises(InvalidTokenError):
            await svc.verify_email(token="bad")

    @pytest.mark.asyncio
    async def test_verify_email_already_verified_raises(self) -> None:
        svc = self._make_svc()
        vt = VerificationToken()
        vt.id = uuid7()
        vt.user_id = self.user.id
        vt.token_hash = hash_token("raw-token")
        vt.expires_at = datetime.now(UTC) + timedelta(hours=1)
        svc._verify_repo.get_valid_by_hash.return_value = vt
        already_verified = make_user(email_verified=True)
        svc._user_repo.get.return_value = already_verified

        with pytest.raises(EmailAlreadyVerifiedError):
            await svc.verify_email(token="raw-token")

    @pytest.mark.asyncio
    async def test_verify_email_success_activates_invited_user(self) -> None:
        svc = self._make_svc()
        vt = VerificationToken()
        vt.id = uuid7()
        vt.user_id = self.user.id
        vt.token_hash = hash_token("raw-token")
        vt.expires_at = datetime.now(UTC) + timedelta(hours=1)
        svc._verify_repo.get_valid_by_hash.return_value = vt
        svc._user_repo.get.return_value = self.user
        svc._verify_repo.mark_used = AsyncMock()
        self.mock_session.flush = AsyncMock()

        returned_user = await svc.verify_email(token="raw-token")
        assert returned_user.email_verified is True
        assert returned_user.status == UserStatus.ACTIVE


class TestAuthServicePasswordReset:
    def setup_method(self) -> None:
        self.settings = _test_settings()
        self.mock_session = AsyncMock()
        self.user = make_user()

    def _make_svc(self) -> Any:
        from app.auth.service import AuthService

        svc = AuthService(self.mock_session, self.settings)
        svc._user_repo = AsyncMock()
        svc._reset_repo = AsyncMock()
        svc._session_repo = AsyncMock()
        return svc

    @pytest.mark.asyncio
    async def test_request_reset_unknown_email_returns_none(self) -> None:
        svc = self._make_svc()
        svc._user_repo.get_by_email.return_value = None

        result = await svc.create_password_reset_token(email="ghost@example.com")
        assert result is None

    @pytest.mark.asyncio
    async def test_request_reset_known_email_returns_token(self) -> None:
        svc = self._make_svc()
        svc._user_repo.get_by_email.return_value = self.user
        svc._reset_repo.invalidate_for_user = AsyncMock()
        svc._reset_repo.create = AsyncMock()

        token = await svc.create_password_reset_token(email=self.user.email)
        assert token is not None
        assert isinstance(token, str)

    @pytest.mark.asyncio
    async def test_reset_password_invalid_token_raises(self) -> None:
        svc = self._make_svc()
        svc._reset_repo.get_valid_by_hash.return_value = None

        with pytest.raises(InvalidTokenError):
            await svc.reset_password(token="bad", new_password="newpassword123")

    @pytest.mark.asyncio
    async def test_reset_password_updates_hash(self) -> None:
        svc = self._make_svc()
        prt = PasswordResetToken()
        prt.id = uuid7()
        prt.user_id = self.user.id
        prt.token_hash = hash_token("raw-token")
        prt.expires_at = datetime.now(UTC) + timedelta(hours=1)
        svc._reset_repo.get_valid_by_hash.return_value = prt
        svc._user_repo.get.return_value = self.user
        svc._reset_repo.mark_used = AsyncMock()
        self.mock_session.flush = AsyncMock()
        svc._session_repo.revoke_all_for_user = AsyncMock()

        await svc.reset_password(token="raw-token", new_password="new-secure-pass!")
        assert self.user.password_hash is not None
        assert verify_password(self.user.password_hash, "new-secure-pass!")


# ─── F-022: get_current_user dependency ──────────────────────────────────────


class TestGetCurrentUserDependency:
    def setup_method(self) -> None:
        self.settings = _test_settings()
        self.user = make_user()

    @pytest.mark.asyncio
    async def test_valid_token_returns_user(self) -> None:
        from app.auth.dependencies import get_current_user

        token = create_access_token(
            user_id=str(self.user.id),
            session_id=str(uuid.uuid4()),
            email=self.user.email,
            settings=self.settings,
        )

        mock_db = AsyncMock()
        mock_user_repo = AsyncMock()
        mock_user_repo.get.return_value = self.user

        with (
            patch("app.auth.dependencies.UserRepository", return_value=mock_user_repo),
            patch("app.auth.dependencies.get_settings", return_value=self.settings),
        ):
            result = await get_current_user(
                request=MagicMock(cookies={}), token=token, db=mock_db, settings=self.settings
            )
        assert result is self.user

    @pytest.mark.asyncio
    async def test_invalid_token_raises_401(self) -> None:
        from fastapi import HTTPException

        from app.auth.dependencies import get_current_user

        mock_db = AsyncMock()
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(
                request=MagicMock(cookies={}),
                token="not.a.valid.jwt",
                db=mock_db,
                settings=self.settings,
            )
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_disabled_user_raises_403(self) -> None:
        from fastapi import HTTPException

        from app.auth.dependencies import get_current_user

        token = create_access_token(
            user_id=str(self.user.id),
            session_id=str(uuid.uuid4()),
            email=self.user.email,
            settings=self.settings,
        )

        disabled = make_user(status=UserStatus.DISABLED)
        mock_db = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get.return_value = disabled

        with (
            patch("app.auth.dependencies.UserRepository", return_value=mock_repo),
            patch("app.auth.dependencies.get_settings", return_value=self.settings),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(
                    request=MagicMock(cookies={}), token=token, db=mock_db, settings=self.settings
                )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_user_not_found_raises_401(self) -> None:
        from fastapi import HTTPException

        from app.auth.dependencies import get_current_user

        token = create_access_token(
            user_id=str(self.user.id),
            session_id=str(uuid.uuid4()),
            email=self.user.email,
            settings=self.settings,
        )

        mock_db = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get.return_value = None

        with (
            patch("app.auth.dependencies.UserRepository", return_value=mock_repo),
            patch("app.auth.dependencies.get_settings", return_value=self.settings),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(
                    request=MagicMock(cookies={}), token=token, db=mock_db, settings=self.settings
                )
        assert exc_info.value.status_code == 401
