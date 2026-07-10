"""Tests for EP-24.4.1 — Authentication Enforcement & First Login Stabilization.

Covers the login-time email-verification bypass fix:
  - AuthService.login() refuses an unverified account (EmailNotVerifiedError)
  - AuthService.login() still succeeds for a verified account
  - AuthService.login() still raises InvalidCredentialsError for a wrong
    password on an unverified account (credentials checked first — no
    verification-status leak ahead of a valid password)
  - AuthService.login() still raises AccountDisabledError for a disabled
    account regardless of verification status
  - register()'s own immediate session issuance for a brand-new (deliberately
    unverified) account is unaffected — this is a separate, unchanged code
    path (see AuthService.login's docstring)
  - login_or_register_with_google() never raises EmailNotVerifiedError —
    Google already verifies the address
  - API layer: POST /v1/auth/login returns 403 with the exact required
    message for an unverified account, and this is not counted as a
    rate-limiter failure
  - A full register -> reject-login -> verify -> login-succeeds journey
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.exceptions import (
    AccountDisabledError,
    EmailNotVerifiedError,
    InvalidCredentialsError,
)
from app.auth.password import hash_password
from app.auth.service import AuthService, TokenPair
from app.config.settings import Settings
from app.models.user import UserStatus
from tests.conftest import make_user

_TEST_PASSWORD = "correct-horse-battery-staple"


def _test_settings(**overrides: Any) -> Settings:
    kwargs: dict[str, Any] = {
        "app_env": "testing",
        "app_secret_key": "test-secret-key-with-at-least-32-chars!!",
        "jwt_secret": "test-jwt-secret-for-unit-tests-only!!",
    }
    kwargs.update(overrides)
    return Settings(**kwargs)


def _make_svc() -> AuthService:
    svc = AuthService(AsyncMock(), _test_settings())
    svc._user_repo = AsyncMock()
    svc._session_repo = AsyncMock()
    svc._membership_repo = AsyncMock()
    return svc


class TestLoginEmailVerificationEnforcement:
    @pytest.mark.asyncio
    async def test_unverified_account_is_rejected(self) -> None:
        svc = _make_svc()
        user = make_user(
            password_hash=hash_password(_TEST_PASSWORD),
            email_verified=False,
        )
        svc._user_repo.get_by_email.return_value = user

        with pytest.raises(EmailNotVerifiedError):
            await svc.login(email=user.email, password=_TEST_PASSWORD)

        svc._session_repo.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_verified_account_logs_in_successfully(self) -> None:
        svc = _make_svc()
        user = make_user(
            password_hash=hash_password(_TEST_PASSWORD),
            email_verified=True,
        )
        svc._user_repo.get_by_email.return_value = user

        pair, returned_user = await svc.login(email=user.email, password=_TEST_PASSWORD)

        assert isinstance(pair, TokenPair)
        assert returned_user is user
        svc._session_repo.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_wrong_password_on_unverified_account_raises_invalid_credentials_not_unverified(
        self,
    ) -> None:
        """Credentials are checked before verification status — a wrong
        password must never leak "this account exists but is unverified"
        ahead of proving the password is even correct."""
        svc = _make_svc()
        user = make_user(
            password_hash=hash_password(_TEST_PASSWORD),
            email_verified=False,
        )
        svc._user_repo.get_by_email.return_value = user

        with pytest.raises(InvalidCredentialsError):
            await svc.login(email=user.email, password="wrong-password")

    @pytest.mark.asyncio
    async def test_disabled_account_raises_disabled_not_unverified(self) -> None:
        svc = _make_svc()
        user = make_user(
            password_hash=hash_password(_TEST_PASSWORD),
            email_verified=False,
            status=UserStatus.DISABLED,
        )
        svc._user_repo.get_by_email.return_value = user

        with pytest.raises(AccountDisabledError):
            await svc.login(email=user.email, password=_TEST_PASSWORD)


class TestRegisterUnaffected:
    @pytest.mark.asyncio
    async def test_register_no_longer_issues_a_session(self) -> None:
        """Superseded by EP-24.6.1: register()'s immediate session issuance
        (the EP-21.2 activation-funnel exception this test used to pin) was
        found to be the production bug reported in EP-24.6.1 Issue 2 — a
        first-time password registrant reaching the dashboard before
        verifying their email. `register()` now mirrors `login()`'s own
        "no session until verified" contract; only a *subsequent* `login()`
        call, made after the email is clicked, ever issues one. See
        `test_ep24_6_1_hotfix.py` for the full regression coverage of the
        new behavior."""
        svc = _make_svc()
        svc._org_repo = AsyncMock()
        svc._org_repo.slug_exists.return_value = False
        svc._verify_repo = AsyncMock()
        svc._email = AsyncMock()
        svc._user_repo.email_exists.return_value = False

        pair, user, org = await svc.register(
            email="brandnew@example.com", password=_TEST_PASSWORD, display_name="Brand New"
        )

        assert pair is None
        assert user.email_verified is False
        assert org is not None
        svc._session_repo.create.assert_not_awaited()


class TestGoogleLoginUnaffected:
    @pytest.mark.asyncio
    async def test_google_login_never_raises_email_not_verified(self) -> None:
        svc = _make_svc()
        svc._org_repo = AsyncMock()
        svc._email = AsyncMock()
        existing = make_user(email="ada@example.com", email_verified=False)
        existing.google_sub = "sub-1"
        svc._user_repo.get_by_google_sub.return_value = existing

        pair, _user, _org, is_new = await svc.login_or_register_with_google(
            google_sub="sub-1",
            email="ada@example.com",
            display_name="Ada",
            avatar_url=None,
        )

        assert isinstance(pair, TokenPair)
        assert is_new is False


# ══════════════════════════════════════════════════════════════════════════════
# API layer
# ══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def app() -> Any:
    from app.main import app as fastapi_app

    return fastapi_app


def _override_settings_and_db(app: Any) -> None:
    from app.api.deps import get_db
    from app.config.settings import get_settings

    async def mock_get_db() -> Any:
        yield AsyncMock()

    app.dependency_overrides[get_settings] = lambda: _test_settings()
    app.dependency_overrides[get_db] = mock_get_db


class TestLoginEndpointRejection:
    @pytest.mark.asyncio
    async def test_returns_403_with_required_message(self, app: Any) -> None:
        _override_settings_and_db(app)
        try:
            with patch("app.api.v1.auth.AuthService") as mock_svc_cls:
                mock_svc_cls.return_value.login = AsyncMock(side_effect=EmailNotVerifiedError)
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(
                        "/v1/auth/login",
                        json={"email": "unverified@example.com", "password": "whatever12345"},
                    )
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Please verify your email before signing in."

    @pytest.mark.asyncio
    async def test_rejection_does_not_count_as_a_rate_limit_failure(self, app: Any) -> None:
        """A correct-password-but-unverified attempt must not push the
        caller toward a login lockout — only wrong passwords should."""
        _override_settings_and_db(app)
        try:
            with patch("app.api.v1.auth.AuthService") as mock_svc_cls:
                mock_svc_cls.return_value.login = AsyncMock(side_effect=EmailNotVerifiedError)
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    last_resp = None
                    for _ in range(4):
                        last_resp = await ac.post(
                            "/v1/auth/login",
                            json={
                                "email": "still-unverified@example.com",
                                "password": "whatever12345",
                            },
                        )
        finally:
            app.dependency_overrides.clear()
        assert last_resp is not None
        # Every attempt is still 403 (unverified), never 429 (rate limited).
        assert last_resp.status_code == 403

    @pytest.mark.asyncio
    async def test_verified_account_login_succeeds_at_the_api_layer(self, app: Any) -> None:
        _override_settings_and_db(app)
        user = make_user(email="verified@example.com", email_verified=True)
        pair = TokenPair(access_token="a", refresh_token="r", expires_in=1800)
        try:
            with patch("app.api.v1.auth.AuthService") as mock_svc_cls:
                mock_svc_cls.return_value.login = AsyncMock(return_value=(pair, user))
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(
                        "/v1/auth/login",
                        json={"email": "verified@example.com", "password": "whatever12345"},
                    )
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 200
        assert resp.json()["access_token"] == "a"


class TestFullJourney:
    @pytest.mark.asyncio
    async def test_register_reject_verify_login_succeeds(self, app: Any) -> None:
        """The exact journey Part 6 asks to be manually verified, pinned as
        an automated regression test at the service layer: register (email
        unverified) -> login rejected -> verify_email -> login succeeds."""
        svc = _make_svc()
        svc._org_repo = AsyncMock()
        svc._verify_repo = AsyncMock()
        svc._email = AsyncMock()
        svc._user_repo.email_exists.return_value = False
        svc._org_repo.slug_exists.return_value = False

        _pair, user, _org = await svc.register(
            email="journey@example.com", password=_TEST_PASSWORD, display_name="Journey"
        )
        assert user.email_verified is False

        # A *separate* login attempt (e.g. after logging out) must be rejected.
        svc._user_repo.get_by_email.return_value = user
        with pytest.raises(EmailNotVerifiedError):
            await svc.login(email=user.email, password=_TEST_PASSWORD)

        # Verify the email — mirrors AuthService.verify_email's own mutation.
        user.email_verified = True

        # Login now succeeds.
        pair2, returned_user = await svc.login(email=user.email, password=_TEST_PASSWORD)
        assert isinstance(pair2, TokenPair)
        assert returned_user is user
