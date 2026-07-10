"""Tests for EP-24.4 — Email Verification, Password Reset, Email Infrastructure.

Covers (all hermetic — no network, no real database):
  - EmailTemplateRenderer: HTML escaping, structure, all three templates
  - ResendEmailProvider: unconfigured skip, success/error paths via httpx.MockTransport
  - EmailService: delegates to provider/renderer, never calls Resend directly
  - EmailRateLimiter: sliding-window allow/block
  - VerificationTokenRepository.invalidate_for_user (replay protection)
  - AuthService: resend_verification_email, verification-email-on-register,
    welcome-email-on-verify, reset-email-on-request, token replay/expiration
  - API: POST /resend-verification, GET+POST /verify-email, POST /forgot-password
    (and its pre-EP-24.4 alias), rate limiting, anti-enumeration responses
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.exceptions import InvalidTokenError
from app.auth.rate_limit import EmailRateLimiter
from app.auth.service import AuthService
from app.config.settings import Settings
from app.db.mixins import uuid7
from app.email.provider import EmailMessage, EmailSendResult
from app.email.renderer import EmailTemplateRenderer
from app.email.resend_provider import ResendEmailProvider
from app.email.service import EmailService
from app.models.user import UserStatus
from app.models.verification_token import VerificationToken
from app.repositories.verification_token_repository import VerificationTokenRepository
from tests.conftest import make_user

_TEST_SECRET = "test-jwt-secret-for-unit-tests-only!!"


def _test_settings(**overrides: Any) -> Settings:
    kwargs: dict[str, Any] = {
        "app_env": "testing",
        "app_secret_key": "test-secret-key-with-at-least-32-chars!!",
        "jwt_secret": _TEST_SECRET,
    }
    kwargs.update(overrides)
    return Settings(**kwargs)


# ══════════════════════════════════════════════════════════════════════════════
# EmailTemplateRenderer — rendering only, no I/O
# ══════════════════════════════════════════════════════════════════════════════


class TestEmailTemplateRenderer:
    def setup_method(self) -> None:
        self.renderer = EmailTemplateRenderer()

    def test_verification_email_contains_link_and_expiry(self) -> None:
        rendered = self.renderer.render_verification_email(
            display_name="Ada Lovelace",
            verify_url="https://app.costorah.com/verify-email?token=abc123",
            expires_hours=24,
            year=2026,
        )
        assert rendered.subject
        assert "abc123" in rendered.html_body
        assert "24 hours" in rendered.html_body
        assert "abc123" in rendered.text_body
        assert "Verify" in rendered.html_body

    def test_verification_email_escapes_display_name(self) -> None:
        rendered = self.renderer.render_verification_email(
            display_name="<script>alert(1)</script>",
            verify_url="https://app.costorah.com/verify-email?token=abc",
            expires_hours=24,
            year=2026,
        )
        assert "<script>alert(1)</script>" not in rendered.html_body
        assert "&lt;script&gt;" in rendered.html_body

    def test_password_reset_email_contains_link_and_expiry(self) -> None:
        rendered = self.renderer.render_password_reset_email(
            display_name="Ada",
            reset_url="https://app.costorah.com/reset-password?token=xyz789",
            expires_hours=1,
            year=2026,
        )
        assert "xyz789" in rendered.html_body
        assert "1 hour" in rendered.html_body
        assert "xyz789" in rendered.text_body

    def test_welcome_email_contains_dashboard_link(self) -> None:
        rendered = self.renderer.render_welcome_email(
            display_name="Ada",
            dashboard_url="https://app.costorah.com/dashboard",
            year=2026,
        )
        assert "https://app.costorah.com/dashboard" in rendered.html_body
        assert "Ada" in rendered.html_body

    def test_html_is_responsive_and_dark_mode_aware(self) -> None:
        rendered = self.renderer.render_verification_email(
            display_name="Ada",
            verify_url="https://app.costorah.com/verify-email?token=abc",
            expires_hours=24,
            year=2026,
        )
        assert "prefers-color-scheme: dark" in rendered.html_body
        assert "max-width: 600px" in rendered.html_body
        assert 'lang="en"' in rendered.html_body

    def test_html_has_no_placeholder_content(self) -> None:
        for rendered in (
            self.renderer.render_verification_email(
                display_name="Ada", verify_url="https://x/v", expires_hours=24, year=2026
            ),
            self.renderer.render_welcome_email(
                display_name="Ada", dashboard_url="https://x/d", year=2026
            ),
            self.renderer.render_password_reset_email(
                display_name="Ada", reset_url="https://x/r", expires_hours=1, year=2026
            ),
        ):
            assert "TODO" not in rendered.html_body
            assert "lorem ipsum" not in rendered.html_body.lower()
            assert "{year}" not in rendered.html_body  # substituted, not left literal


# ══════════════════════════════════════════════════════════════════════════════
# ResendEmailProvider — transport, EP-24.4 Part 3
# ══════════════════════════════════════════════════════════════════════════════


class TestResendEmailProvider:
    @pytest.mark.asyncio
    async def test_unconfigured_provider_skips_without_network_call(self) -> None:
        provider = ResendEmailProvider(api_key=None, from_email=None)
        result = await provider.send_email(
            EmailMessage(to="a@example.com", subject="s", html_body="<p>h</p>", text_body="t")
        )
        assert result.success is False
        assert result.skipped is True
        await provider.aclose()

    @pytest.mark.asyncio
    async def test_missing_from_email_only_still_skips(self) -> None:
        provider = ResendEmailProvider(api_key="re_test", from_email=None)
        result = await provider.send_email(
            EmailMessage(to="a@example.com", subject="s", html_body="<p>h</p>", text_body="t")
        )
        assert result.skipped is True
        await provider.aclose()

    @pytest.mark.asyncio
    async def test_successful_send_returns_message_id(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/emails"
            assert request.headers["authorization"] == "Bearer re_test_key"
            return httpx.Response(200, json={"id": "msg_abc123"})

        provider = ResendEmailProvider(
            api_key="re_test_key",
            from_email="noreply@costorah.com",
            mock_transport=httpx.MockTransport(handler),
        )
        result = await provider.send_email(
            EmailMessage(
                to="a@example.com",
                subject="Verify your email",
                html_body="<p>hi</p>",
                text_body="hi",
                tags={"category": "verification"},
            )
        )
        assert result.success is True
        assert result.provider_message_id == "msg_abc123"
        await provider.aclose()

    @pytest.mark.asyncio
    async def test_provider_error_status_does_not_raise(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(422, json={"message": "invalid recipient"})

        provider = ResendEmailProvider(
            api_key="re_test_key",
            from_email="noreply@costorah.com",
            mock_transport=httpx.MockTransport(handler),
        )
        result = await provider.send_email(
            EmailMessage(to="bad", subject="s", html_body="<p>h</p>", text_body="t")
        )
        assert result.success is False
        assert result.skipped is False
        await provider.aclose()

    @pytest.mark.asyncio
    async def test_network_error_does_not_raise(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        provider = ResendEmailProvider(
            api_key="re_test_key",
            from_email="noreply@costorah.com",
            mock_transport=httpx.MockTransport(handler),
        )
        result = await provider.send_email(
            EmailMessage(to="a@example.com", subject="s", html_body="<p>h</p>", text_body="t")
        )
        assert result.success is False
        assert result.error == "network_error"
        await provider.aclose()

    @pytest.mark.asyncio
    async def test_never_logs_api_key(self) -> None:
        """The API key must never appear in a log call's kwargs."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"id": "msg_1"})

        provider = ResendEmailProvider(
            api_key="re_super_secret_key",
            from_email="noreply@costorah.com",
            mock_transport=httpx.MockTransport(handler),
        )
        with patch("app.email.resend_provider.log") as mock_log:
            await provider.send_email(
                EmailMessage(to="a@example.com", subject="s", html_body="<p>h</p>", text_body="t")
            )
            for call in mock_log.mock_calls:
                assert "re_super_secret_key" not in str(call)
        await provider.aclose()


# ══════════════════════════════════════════════════════════════════════════════
# EmailService — business logic, never calls Resend directly (Part 3)
# ══════════════════════════════════════════════════════════════════════════════


class TestEmailService:
    def _service_with_fake_provider(self) -> tuple[EmailService, AsyncMock]:
        fake_provider = AsyncMock()
        fake_provider.send_email.return_value = EmailSendResult(success=True)
        settings = _test_settings()
        service = EmailService(settings, provider=fake_provider)
        return service, fake_provider

    @pytest.mark.asyncio
    async def test_send_verification_email_never_touches_resend_directly(self) -> None:
        service, fake_provider = self._service_with_fake_provider()
        await service.send_verification_email(
            to="a@example.com", display_name="Ada", verify_url="https://x/v"
        )
        fake_provider.send_email.assert_awaited_once()
        message: EmailMessage = fake_provider.send_email.call_args.args[0]
        assert message.to == "a@example.com"
        assert message.tags["category"] == "verification"

    @pytest.mark.asyncio
    async def test_send_welcome_email_uses_dashboard_url_from_settings(self) -> None:
        settings = _test_settings(dashboard_url="https://app.costorah.com")
        fake_provider = AsyncMock()
        fake_provider.send_email.return_value = EmailSendResult(success=True)
        service = EmailService(settings, provider=fake_provider)
        await service.send_welcome_email(to="a@example.com", display_name="Ada")
        message: EmailMessage = fake_provider.send_email.call_args.args[0]
        assert "app.costorah.com" in message.html_body

    @pytest.mark.asyncio
    async def test_send_password_reset_email_tags_correctly(self) -> None:
        service, fake_provider = self._service_with_fake_provider()
        await service.send_password_reset_email(
            to="a@example.com", display_name="Ada", reset_url="https://x/r"
        )
        message: EmailMessage = fake_provider.send_email.call_args.args[0]
        assert message.tags["category"] == "password_reset"

    @pytest.mark.asyncio
    async def test_default_construction_builds_resend_provider_from_settings(self) -> None:
        """No explicit provider passed — EmailService must build its own
        ResendEmailProvider from Settings, never require a caller to wire
        Resend up manually (Part 3's core requirement)."""
        settings = _test_settings()
        service = EmailService(settings)
        assert isinstance(service._provider, ResendEmailProvider)
        await service.aclose()

    @pytest.mark.asyncio
    async def test_delivery_failure_does_not_raise(self) -> None:
        fake_provider = AsyncMock()
        fake_provider.send_email.return_value = EmailSendResult(success=False, error="boom")
        service = EmailService(_test_settings(), provider=fake_provider)
        result = await service.send_verification_email(
            to="a@example.com", display_name="Ada", verify_url="https://x/v"
        )
        assert result.success is False


# ══════════════════════════════════════════════════════════════════════════════
# EmailRateLimiter — sliding window (Part 5 / Part 9)
# ══════════════════════════════════════════════════════════════════════════════


class TestEmailRateLimiter:
    @pytest.mark.asyncio
    async def test_allows_up_to_max_attempts_then_blocks(self) -> None:
        limiter = EmailRateLimiter(max_attempts=3, window_seconds=60)
        for _ in range(3):
            decision = await limiter.check_and_record(scope="verify", key="a@example.com")
            assert decision.allowed is True
        blocked = await limiter.check_and_record(scope="verify", key="a@example.com")
        assert blocked.allowed is False
        assert blocked.retry_after_seconds == 60

    @pytest.mark.asyncio
    async def test_scopes_are_independent(self) -> None:
        limiter = EmailRateLimiter(max_attempts=1, window_seconds=60)
        first = await limiter.check_and_record(scope="verify", key="a@example.com")
        second = await limiter.check_and_record(scope="reset", key="a@example.com")
        assert first.allowed is True
        assert second.allowed is True

    @pytest.mark.asyncio
    async def test_keys_are_independent(self) -> None:
        limiter = EmailRateLimiter(max_attempts=1, window_seconds=60)
        a = await limiter.check_and_record(scope="verify", key="a@example.com")
        b = await limiter.check_and_record(scope="verify", key="b@example.com")
        assert a.allowed is True
        assert b.allowed is True


# ══════════════════════════════════════════════════════════════════════════════
# VerificationTokenRepository.invalidate_for_user — replay protection
# ══════════════════════════════════════════════════════════════════════════════


class TestVerificationTokenRepositoryInvalidate:
    @pytest.mark.asyncio
    async def test_invalidate_for_user_executes_update(self) -> None:
        session = AsyncMock()
        repo = VerificationTokenRepository(session)
        user_id = uuid.uuid4()
        await repo.invalidate_for_user(user_id)
        session.execute.assert_awaited_once()


# ══════════════════════════════════════════════════════════════════════════════
# AuthService — verification email on register, resend, replay, welcome email
# ══════════════════════════════════════════════════════════════════════════════


class TestAuthServiceVerificationEmailFlow:
    def _make_svc(self) -> tuple[AuthService, AsyncMock]:
        settings = _test_settings()
        mock_session = AsyncMock()
        svc = AuthService(mock_session, settings)
        svc._user_repo = AsyncMock()
        svc._verify_repo = AsyncMock()
        svc._reset_repo = AsyncMock()
        fake_email = AsyncMock()
        fake_email.send_verification_email.return_value = EmailSendResult(success=True)
        fake_email.send_welcome_email.return_value = EmailSendResult(success=True)
        fake_email.send_password_reset_email.return_value = EmailSendResult(success=True)
        svc._email = fake_email
        return svc, fake_email

    @pytest.mark.asyncio
    async def test_create_verification_token_invalidates_previous_tokens_first(self) -> None:
        svc, _ = self._make_svc()
        user_id = uuid.uuid4()
        await svc.create_verification_token(user_id=user_id)
        svc._verify_repo.invalidate_for_user.assert_awaited_once_with(user_id)
        svc._verify_repo.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_resend_verification_sends_for_unverified_existing_user(self) -> None:
        svc, fake_email = self._make_svc()
        user = make_user(email_verified=False)
        svc._user_repo.get_by_email.return_value = user
        await svc.resend_verification_email(email=user.email)
        fake_email.send_verification_email.assert_awaited_once()
        call_kwargs = fake_email.send_verification_email.call_args.kwargs
        assert call_kwargs["to"] == user.email
        assert "verify-email?token=" in call_kwargs["verify_url"]

    @pytest.mark.asyncio
    async def test_resend_verification_silent_for_already_verified(self) -> None:
        svc, fake_email = self._make_svc()
        user = make_user(email_verified=True)
        svc._user_repo.get_by_email.return_value = user
        await svc.resend_verification_email(email=user.email)
        fake_email.send_verification_email.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_resend_verification_silent_for_unknown_email(self) -> None:
        svc, fake_email = self._make_svc()
        svc._user_repo.get_by_email.return_value = None
        await svc.resend_verification_email(email="ghost@example.com")
        fake_email.send_verification_email.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_verify_email_sends_welcome_email_on_success(self) -> None:
        svc, fake_email = self._make_svc()
        user = make_user(email_verified=False, status=UserStatus.INVITED)
        vt = VerificationToken()
        vt.id = uuid7()
        vt.user_id = user.id
        vt.expires_at = datetime.now(UTC) + timedelta(hours=1)
        svc._verify_repo.get_valid_by_hash.return_value = vt
        svc._user_repo.get.return_value = user
        svc._session.flush = AsyncMock()

        result = await svc.verify_email(token="raw-token")

        assert result.email_verified is True
        fake_email.send_welcome_email.assert_awaited_once_with(
            to=user.email, display_name=user.display_name
        )

    @pytest.mark.asyncio
    async def test_verify_email_invalid_token_does_not_send_welcome_email(self) -> None:
        svc, fake_email = self._make_svc()
        svc._verify_repo.get_valid_by_hash.return_value = None
        with pytest.raises(InvalidTokenError):
            await svc.verify_email(token="bad")
        fake_email.send_welcome_email.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_create_password_reset_token_sends_email(self) -> None:
        svc, fake_email = self._make_svc()
        user = make_user()
        svc._user_repo.get_by_email.return_value = user

        raw = await svc.create_password_reset_token(email=user.email)

        assert raw is not None
        fake_email.send_password_reset_email.assert_awaited_once()
        call_kwargs = fake_email.send_password_reset_email.call_args.kwargs
        assert "reset-password?token=" in call_kwargs["reset_url"]

    @pytest.mark.asyncio
    async def test_create_password_reset_token_unknown_email_sends_nothing(self) -> None:
        svc, fake_email = self._make_svc()
        svc._user_repo.get_by_email.return_value = None

        raw = await svc.create_password_reset_token(email="ghost@example.com")

        assert raw is None
        fake_email.send_password_reset_email.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_register_sends_verification_email(self) -> None:
        settings = _test_settings()
        mock_session = AsyncMock()
        svc = AuthService(mock_session, settings)
        svc._user_repo = AsyncMock()
        svc._org_repo = AsyncMock()
        svc._membership_repo = AsyncMock()
        svc._verify_repo = AsyncMock()
        svc._session_repo = AsyncMock()
        svc._user_repo.email_exists.return_value = False
        svc._org_repo.slug_exists.return_value = False
        fake_email = AsyncMock()
        fake_email.send_verification_email.return_value = EmailSendResult(success=True)
        svc._email = fake_email

        await svc.register(email="new@example.com", password="password123", display_name="New")

        fake_email.send_verification_email.assert_awaited_once()
        assert fake_email.send_verification_email.call_args.kwargs["to"] == "new@example.com"


# ══════════════════════════════════════════════════════════════════════════════
# API layer — resend-verification, GET/POST verify-email, forgot-password
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


class TestResendVerificationEndpoint:
    @pytest.mark.asyncio
    async def test_returns_generic_message_regardless_of_outcome(self, app: Any) -> None:
        _override_settings_and_db(app)
        try:
            with patch("app.api.v1.auth.AuthService") as mock_svc:
                mock_svc.return_value.resend_verification_email = AsyncMock()
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(
                        "/v1/auth/resend-verification", json={"email": "a@example.com"}
                    )
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 200
        assert "If an account" in resp.json()["message"]

    @pytest.mark.asyncio
    async def test_rate_limited_after_max_attempts(self, app: Any) -> None:
        _override_settings_and_db(app)
        try:
            with patch("app.api.v1.auth.AuthService") as mock_svc:
                mock_svc.return_value.resend_verification_email = AsyncMock()
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    last_resp = None
                    for _ in range(4):
                        last_resp = await ac.post(
                            "/v1/auth/resend-verification",
                            json={"email": "rate-limit-test@example.com"},
                        )
        finally:
            app.dependency_overrides.clear()
        assert last_resp is not None
        assert last_resp.status_code == 429
        assert "Retry-After" in last_resp.headers


class TestVerifyEmailEndpoints:
    @pytest.mark.asyncio
    async def test_get_variant_success(self, app: Any) -> None:
        _override_settings_and_db(app)
        try:
            with patch("app.api.v1.auth.AuthService") as mock_svc:
                mock_svc.return_value.verify_email = AsyncMock()
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.get("/v1/auth/verify-email", params={"token": "raw-token"})
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 200
        assert resp.json()["message"] == "Email verified successfully"

    @pytest.mark.asyncio
    async def test_get_variant_already_verified_returns_200_not_409(self, app: Any) -> None:
        from app.auth.exceptions import EmailAlreadyVerifiedError

        _override_settings_and_db(app)
        try:
            with patch("app.api.v1.auth.AuthService") as mock_svc:
                mock_svc.return_value.verify_email = AsyncMock(
                    side_effect=EmailAlreadyVerifiedError
                )
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.get("/v1/auth/verify-email", params={"token": "raw-token"})
        finally:
            app.dependency_overrides.clear()
        # EP-24.4 Part 1: "If user already verified: return success."
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_invalid_token_returns_400_without_revealing_detail(self, app: Any) -> None:
        _override_settings_and_db(app)
        try:
            with patch("app.api.v1.auth.AuthService") as mock_svc:
                mock_svc.return_value.verify_email = AsyncMock(side_effect=InvalidTokenError("x"))
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.get("/v1/auth/verify-email", params={"token": "bad"})
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Verification token is invalid or expired"

    @pytest.mark.asyncio
    async def test_post_variant_still_works(self, app: Any) -> None:
        _override_settings_and_db(app)
        try:
            with patch("app.api.v1.auth.AuthService") as mock_svc:
                mock_svc.return_value.verify_email = AsyncMock()
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post("/v1/auth/verify-email", json={"token": "raw-token"})
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 200


class TestForgotPasswordEndpoint:
    @pytest.mark.asyncio
    async def test_forgot_password_returns_generic_message(self, app: Any) -> None:
        _override_settings_and_db(app)
        try:
            with patch("app.api.v1.auth.AuthService") as mock_svc:
                mock_svc.return_value.create_password_reset_token = AsyncMock(return_value=None)
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(
                        "/v1/auth/forgot-password", json={"email": "ghost@example.com"}
                    )
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 200
        assert "If an account with that email exists" in resp.json()["message"]

    @pytest.mark.asyncio
    async def test_legacy_alias_still_mounted_and_behaves_identically(self, app: Any) -> None:
        _override_settings_and_db(app)
        try:
            with patch("app.api.v1.auth.AuthService") as mock_svc:
                mock_svc.return_value.create_password_reset_token = AsyncMock(return_value=None)
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(
                        "/v1/auth/request-password-reset", json={"email": "ghost@example.com"}
                    )
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 200
        assert "If an account with that email exists" in resp.json()["message"]

    @pytest.mark.asyncio
    async def test_rate_limited_after_max_attempts(self, app: Any) -> None:
        _override_settings_and_db(app)
        try:
            with patch("app.api.v1.auth.AuthService") as mock_svc:
                mock_svc.return_value.create_password_reset_token = AsyncMock(return_value=None)
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    last_resp = None
                    for _ in range(4):
                        last_resp = await ac.post(
                            "/v1/auth/forgot-password",
                            json={"email": "rate-limit-reset@example.com"},
                        )
        finally:
            app.dependency_overrides.clear()
        assert last_resp is not None
        assert last_resp.status_code == 429
