"""Tests for EP-24.5 — Google OAuth & Social Identity.

Covers (all hermetic — no real network, no real database, no real Google
credentials — a real in-memory RSA keypair signs test ID tokens and a fake
``SigningKeyResolver`` stands in for PyJWKClient's network JWKS fetch):

  - app.auth.google_oauth: PKCE, OAuth state JWT encode/decode/match, the
    authorize-URL builder, the token-exchange call (httpx.MockTransport),
    and ID token verification (valid, bad signature, wrong issuer, wrong
    audience, expired, nonce mismatch, unverified email).
  - AuthService: login_or_register_with_google (new user, existing-email
    auto-link, existing google_sub -> login), link_google (success,
    already-linked-to-a-different-user), unlink_google (success, refused
    when the account has no password).
  - API: GET /google/start (503 unconfigured, redirect + state cookie),
    POST /google/link (auth required, returns authorize_url + cookie),
    GET /google/callback (state mismatch, invalid token, new-user
    registration, existing-user login, link mode, already-linked), POST
    /google/unlink (200, 400 last-auth-method).
"""

from __future__ import annotations

import base64
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient

from app.auth import google_oauth
from app.auth.exceptions import GoogleAccountAlreadyLinkedError, LastAuthMethodError
from app.auth.google_oauth import (
    GoogleIdentity,
    GoogleOAuthNotConfiguredError,
    InvalidGoogleTokenError,
    OAuthStateError,
)
from app.auth.service import AuthService, TokenPair
from app.config.settings import Settings
from app.models.user import User, UserStatus
from tests.conftest import make_org, make_user

_TEST_SECRET = "test-jwt-secret-for-unit-tests-only!!"


def _test_settings(**overrides: Any) -> Settings:
    kwargs: dict[str, Any] = {
        "app_env": "testing",
        "app_secret_key": "test-secret-key-with-at-least-32-chars!!",
        "jwt_secret": _TEST_SECRET,
    }
    kwargs.update(overrides)
    return Settings(**kwargs)


def _google_settings(**overrides: Any) -> Settings:
    return _test_settings(
        google_client_id="test-client-id.apps.googleusercontent.com",
        google_client_secret="test-client-secret",
        api_base_url="https://api.test.costorah.com",
        dashboard_url="https://app.test.costorah.com",
        **overrides,
    )


# ── Real RSA keypair for signing test Google ID tokens ──────────────────────

_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PUBLIC_KEY = _PRIVATE_KEY.public_key()


class _FakeSigningKey:
    def __init__(self, key: Any) -> None:
        self.key = key


class _FakeResolver:
    """Stands in for jwt.PyJWKClient — no network JWKS fetch."""

    def __init__(self, key: Any = _PUBLIC_KEY, *, raise_error: bool = False) -> None:
        self._key = key
        self._raise_error = raise_error

    def get_signing_key_from_jwt(self, token: str) -> _FakeSigningKey:
        if self._raise_error:
            raise RuntimeError("JWKS fetch failed")
        return _FakeSigningKey(self._key)


def _make_id_token(
    *,
    sub: str = "google-sub-123",
    email: str = "ada@example.com",
    email_verified: bool = True,
    nonce: str = "expected-nonce",
    issuer: str = "https://accounts.google.com",
    audience: str = "test-client-id.apps.googleusercontent.com",
    expires_delta: timedelta = timedelta(minutes=5),
    name: str | None = "Ada Lovelace",
    picture: str | None = "https://example.com/avatar.png",
    private_key: Any = _PRIVATE_KEY,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "iss": issuer,
        "aud": audience,
        "sub": sub,
        "email": email,
        "email_verified": email_verified,
        "nonce": nonce,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
    }
    if name is not None:
        payload["name"] = name
    if picture is not None:
        payload["picture"] = picture
    return jwt.encode(payload, private_key, algorithm="RS256")


# ══════════════════════════════════════════════════════════════════════════════
# PKCE + OAuth state JWT
# ══════════════════════════════════════════════════════════════════════════════


class TestPkce:
    def test_challenge_is_deterministic_for_a_given_verifier(self) -> None:
        pair = google_oauth.generate_pkce_pair()
        assert google_oauth.pkce_challenge_from_verifier(pair.verifier) == pair.challenge

    def test_different_verifiers_produce_different_challenges(self) -> None:
        a = google_oauth.generate_pkce_pair()
        b = google_oauth.generate_pkce_pair()
        assert a.verifier != b.verifier
        assert a.challenge != b.challenge


class TestOAuthState:
    def test_round_trip_login_mode(self) -> None:
        settings = _google_settings()
        token, flow = google_oauth.encode_oauth_state(
            mode="login", redirect_path="/", settings=settings
        )
        decoded = google_oauth.decode_oauth_state(token, settings=settings)
        assert decoded.mode == "login"
        assert decoded.nonce == flow.nonce
        assert decoded.code_verifier == flow.code_verifier
        assert decoded.user_id is None

    def test_round_trip_link_mode_carries_user_id(self) -> None:
        settings = _google_settings()
        user_id = str(uuid.uuid4())
        token, _ = google_oauth.encode_oauth_state(
            mode="link", redirect_path="/settings", settings=settings, user_id=user_id
        )
        decoded = google_oauth.decode_oauth_state(token, settings=settings)
        assert decoded.mode == "link"
        assert decoded.user_id == user_id

    def test_tampered_token_is_rejected(self) -> None:
        settings = _google_settings()
        token, _ = google_oauth.encode_oauth_state(
            mode="login", redirect_path="/", settings=settings
        )
        tampered = token[:-2] + ("aa" if not token.endswith("aa") else "bb")
        with pytest.raises(OAuthStateError):
            google_oauth.decode_oauth_state(tampered, settings=settings)

    def test_expired_token_is_rejected(self) -> None:
        settings = _google_settings()
        now = datetime.now(UTC)
        payload = {
            "csrf_id": "x",
            "nonce": "y",
            "code_verifier": "z",
            "mode": "login",
            "redirect_path": "/",
            "user_id": None,
            "iat": int((now - timedelta(minutes=20)).timestamp()),
            "exp": int((now - timedelta(minutes=10)).timestamp()),
        }
        expired = jwt.encode(
            payload, settings.jwt_secret.get_secret_value(), algorithm=settings.jwt_algorithm
        )
        with pytest.raises(OAuthStateError):
            google_oauth.decode_oauth_state(expired, settings=settings)

    def test_malformed_token_is_rejected(self) -> None:
        settings = _google_settings()
        with pytest.raises(OAuthStateError):
            google_oauth.decode_oauth_state("not-a-jwt", settings=settings)


class TestVerifyStateMatch:
    def test_matching_values_pass(self) -> None:
        google_oauth.verify_state_match(cookie_value="abc", query_value="abc")

    def test_mismatched_values_raise(self) -> None:
        with pytest.raises(OAuthStateError):
            google_oauth.verify_state_match(cookie_value="abc", query_value="xyz")

    def test_missing_cookie_raises(self) -> None:
        with pytest.raises(OAuthStateError):
            google_oauth.verify_state_match(cookie_value=None, query_value="abc")

    def test_missing_query_raises(self) -> None:
        with pytest.raises(OAuthStateError):
            google_oauth.verify_state_match(cookie_value="abc", query_value=None)


# ══════════════════════════════════════════════════════════════════════════════
# Authorize URL
# ══════════════════════════════════════════════════════════════════════════════


class TestBuildAuthorizeUrl:
    def test_builds_expected_query_params(self) -> None:
        settings = _google_settings()
        url = google_oauth.build_authorize_url(
            settings=settings,
            redirect_uri="https://api.test.costorah.com/v1/auth/google/callback",
            state="state-token",
            nonce="nonce-value",
            code_challenge="challenge-value",
        )
        parsed = urlparse(url)
        assert parsed.netloc == "accounts.google.com"
        qs = parse_qs(parsed.query)
        assert qs["client_id"] == [settings.google_client_id]
        assert qs["state"] == ["state-token"]
        assert qs["nonce"] == ["nonce-value"]
        assert qs["code_challenge"] == ["challenge-value"]
        assert qs["code_challenge_method"] == ["S256"]
        assert qs["response_type"] == ["code"]
        assert "openid" in qs["scope"][0]

    def test_raises_when_not_configured(self) -> None:
        settings = _test_settings()
        with pytest.raises(GoogleOAuthNotConfiguredError):
            google_oauth.build_authorize_url(
                settings=settings,
                redirect_uri="https://x/callback",
                state="s",
                nonce="n",
                code_challenge="c",
            )

    def test_login_hint_included_when_given(self) -> None:
        settings = _google_settings()
        url = google_oauth.build_authorize_url(
            settings=settings,
            redirect_uri="https://x/callback",
            state="s",
            nonce="n",
            code_challenge="c",
            login_hint="ada@example.com",
        )
        assert "login_hint=ada%40example.com" in url


# ══════════════════════════════════════════════════════════════════════════════
# Token exchange
# ══════════════════════════════════════════════════════════════════════════════


class TestExchangeCodeForTokens:
    @pytest.mark.asyncio
    async def test_success_returns_token_body(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/token"
            body = request.read().decode()
            assert "code=auth-code" in body
            assert "code_verifier=verifier-abc" in body
            return httpx.Response(200, json={"id_token": "fake-id-token", "access_token": "at"})

        from app.http.transport import HttpxTransport

        transport = HttpxTransport(mock_transport=httpx.MockTransport(handler))
        settings = _google_settings()
        result = await google_oauth.exchange_code_for_tokens(
            settings=settings,
            code="auth-code",
            redirect_uri="https://x/callback",
            code_verifier="verifier-abc",
            transport=transport,
        )
        assert result["id_token"] == "fake-id-token"
        await transport.aclose()

    @pytest.mark.asyncio
    async def test_non_200_raises_token_exchange_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"error": "invalid_grant"})

        from app.http.transport import HttpxTransport

        transport = HttpxTransport(mock_transport=httpx.MockTransport(handler))
        settings = _google_settings()
        with pytest.raises(google_oauth.GoogleTokenExchangeError):
            await google_oauth.exchange_code_for_tokens(
                settings=settings,
                code="bad-code",
                redirect_uri="https://x/callback",
                code_verifier="v",
                transport=transport,
            )
        await transport.aclose()

    @pytest.mark.asyncio
    async def test_missing_id_token_raises(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"access_token": "at"})

        from app.http.transport import HttpxTransport

        transport = HttpxTransport(mock_transport=httpx.MockTransport(handler))
        settings = _google_settings()
        with pytest.raises(google_oauth.GoogleTokenExchangeError):
            await google_oauth.exchange_code_for_tokens(
                settings=settings,
                code="c",
                redirect_uri="https://x/callback",
                code_verifier="v",
                transport=transport,
            )
        await transport.aclose()

    @pytest.mark.asyncio
    async def test_raises_when_not_configured(self) -> None:
        settings = _test_settings()
        with pytest.raises(GoogleOAuthNotConfiguredError):
            await google_oauth.exchange_code_for_tokens(
                settings=settings, code="c", redirect_uri="https://x", code_verifier="v"
            )

    @pytest.mark.asyncio
    async def test_network_error_raises_token_exchange_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        from app.http.transport import HttpxTransport

        transport = HttpxTransport(mock_transport=httpx.MockTransport(handler))
        settings = _google_settings()
        with pytest.raises(google_oauth.GoogleTokenExchangeError):
            await google_oauth.exchange_code_for_tokens(
                settings=settings,
                code="c",
                redirect_uri="https://x/callback",
                code_verifier="v",
                transport=transport,
            )
        await transport.aclose()


# ══════════════════════════════════════════════════════════════════════════════
# ID token verification — Part 1 / Part 9
# ══════════════════════════════════════════════════════════════════════════════


class TestVerifyGoogleIdToken:
    def test_valid_token_returns_identity(self) -> None:
        settings = _google_settings()
        token = _make_id_token()
        identity = google_oauth.verify_google_id_token(
            id_token=token,
            settings=settings,
            expected_nonce="expected-nonce",
            signing_key_resolver=_FakeResolver(),
        )
        assert isinstance(identity, GoogleIdentity)
        assert identity.sub == "google-sub-123"
        assert identity.email == "ada@example.com"
        assert identity.display_name == "Ada Lovelace"
        assert identity.avatar_url == "https://example.com/avatar.png"

    def test_bad_signature_rejected(self) -> None:
        settings = _google_settings()
        other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        token = _make_id_token(private_key=other_key)
        with pytest.raises(InvalidGoogleTokenError):
            google_oauth.verify_google_id_token(
                id_token=token,
                settings=settings,
                expected_nonce="expected-nonce",
                signing_key_resolver=_FakeResolver(),
            )

    def test_wrong_issuer_rejected(self) -> None:
        settings = _google_settings()
        token = _make_id_token(issuer="https://evil.example.com")
        with pytest.raises(InvalidGoogleTokenError):
            google_oauth.verify_google_id_token(
                id_token=token,
                settings=settings,
                expected_nonce="expected-nonce",
                signing_key_resolver=_FakeResolver(),
            )

    def test_alternate_accounts_google_com_issuer_accepted(self) -> None:
        settings = _google_settings()
        token = _make_id_token(issuer="accounts.google.com")
        identity = google_oauth.verify_google_id_token(
            id_token=token,
            settings=settings,
            expected_nonce="expected-nonce",
            signing_key_resolver=_FakeResolver(),
        )
        assert identity.sub == "google-sub-123"

    def test_wrong_audience_rejected(self) -> None:
        settings = _google_settings()
        token = _make_id_token(audience="someone-elses-client-id")
        with pytest.raises(InvalidGoogleTokenError):
            google_oauth.verify_google_id_token(
                id_token=token,
                settings=settings,
                expected_nonce="expected-nonce",
                signing_key_resolver=_FakeResolver(),
            )

    def test_expired_token_rejected(self) -> None:
        settings = _google_settings()
        token = _make_id_token(expires_delta=timedelta(minutes=-5))
        with pytest.raises(InvalidGoogleTokenError):
            google_oauth.verify_google_id_token(
                id_token=token,
                settings=settings,
                expected_nonce="expected-nonce",
                signing_key_resolver=_FakeResolver(),
            )

    def test_nonce_mismatch_rejected(self) -> None:
        settings = _google_settings()
        token = _make_id_token(nonce="actual-nonce")
        with pytest.raises(InvalidGoogleTokenError):
            google_oauth.verify_google_id_token(
                id_token=token,
                settings=settings,
                expected_nonce="different-nonce",
                signing_key_resolver=_FakeResolver(),
            )

    def test_unverified_email_rejected(self) -> None:
        settings = _google_settings()
        token = _make_id_token(email_verified=False)
        with pytest.raises(InvalidGoogleTokenError):
            google_oauth.verify_google_id_token(
                id_token=token,
                settings=settings,
                expected_nonce="expected-nonce",
                signing_key_resolver=_FakeResolver(),
            )

    def test_missing_name_falls_back_to_email_local_part(self) -> None:
        settings = _google_settings()
        token = _make_id_token(name=None, email="grace@example.com")
        identity = google_oauth.verify_google_id_token(
            id_token=token,
            settings=settings,
            expected_nonce="expected-nonce",
            signing_key_resolver=_FakeResolver(),
        )
        assert identity.display_name == "grace"

    def test_jwks_resolution_failure_maps_to_invalid_token_error(self) -> None:
        settings = _google_settings()
        token = _make_id_token()
        with pytest.raises(InvalidGoogleTokenError):
            google_oauth.verify_google_id_token(
                id_token=token,
                settings=settings,
                expected_nonce="expected-nonce",
                signing_key_resolver=_FakeResolver(raise_error=True),
            )

    def test_raises_when_not_configured(self) -> None:
        settings = _test_settings()
        with pytest.raises(GoogleOAuthNotConfiguredError):
            google_oauth.verify_google_id_token(
                id_token="x",
                settings=settings,
                expected_nonce="n",
                signing_key_resolver=_FakeResolver(),
            )


# ══════════════════════════════════════════════════════════════════════════════
# AuthService — Google login/register/link/unlink
# ══════════════════════════════════════════════════════════════════════════════


class TestLoginOrRegisterWithGoogle:
    def _make_svc(self) -> AuthService:
        settings = _google_settings()
        mock_session = AsyncMock()
        svc = AuthService(mock_session, settings)
        svc._user_repo = AsyncMock()
        svc._org_repo = AsyncMock()
        svc._membership_repo = AsyncMock()
        svc._session_repo = AsyncMock()
        svc._email = AsyncMock()
        return svc

    @pytest.mark.asyncio
    async def test_new_user_registers_with_verified_email_and_workspace(self) -> None:
        svc = self._make_svc()
        svc._user_repo.get_by_google_sub.return_value = None
        svc._user_repo.get_by_email.return_value = None
        svc._org_repo.slug_exists.return_value = False

        pair, user, org, is_new = await svc.login_or_register_with_google(
            google_sub="sub-1",
            email="new@example.com",
            display_name="New User",
            avatar_url="https://x/avatar.png",
        )

        assert is_new is True
        assert isinstance(pair, TokenPair)
        assert user.email_verified is True
        assert user.google_sub == "sub-1"
        assert org is not None
        svc._email.send_verification_email.assert_not_awaited()
        svc._email.send_welcome_email.assert_awaited_once()
        svc._user_repo.update_last_login.assert_awaited_once_with(user.id, provider="google")

    @pytest.mark.asyncio
    async def test_existing_email_auto_links_without_duplicate_user(self) -> None:
        svc = self._make_svc()
        existing = make_user(email="ada@example.com")
        svc._user_repo.get_by_google_sub.return_value = None
        svc._user_repo.get_by_email.return_value = existing

        _pair, user, org, is_new = await svc.login_or_register_with_google(
            google_sub="sub-2",
            email="ada@example.com",
            display_name="Ada",
            avatar_url=None,
        )

        assert is_new is False
        assert user is existing
        assert user.google_sub == "sub-2"
        assert org is None
        svc._user_repo.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_existing_google_sub_logs_in(self) -> None:
        svc = self._make_svc()
        existing = make_user(email="ada@example.com")
        existing.google_sub = "sub-3"
        svc._user_repo.get_by_google_sub.return_value = existing

        _pair, user, org, is_new = await svc.login_or_register_with_google(
            google_sub="sub-3",
            email="ada@example.com",
            display_name="Ada",
            avatar_url=None,
        )

        assert is_new is False
        assert user is existing
        assert org is None
        svc._user_repo.get_by_email.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_disabled_account_raises(self) -> None:
        from app.auth.exceptions import AccountDisabledError

        svc = self._make_svc()
        existing = make_user(status=UserStatus.DISABLED)
        existing.google_sub = "sub-4"
        svc._user_repo.get_by_google_sub.return_value = existing

        with pytest.raises(AccountDisabledError):
            await svc.login_or_register_with_google(
                google_sub="sub-4", email=existing.email, display_name="X", avatar_url=None
            )


class TestLinkGoogle:
    def _make_svc(self) -> AuthService:
        settings = _google_settings()
        svc = AuthService(AsyncMock(), settings)
        svc._user_repo = AsyncMock()
        return svc

    @pytest.mark.asyncio
    async def test_links_successfully(self) -> None:
        svc = self._make_svc()
        svc._user_repo.get_by_google_sub.return_value = None
        user = make_user()

        result = await svc.link_google(user=user, google_sub="sub-5", google_email="ada@g.com")

        assert result.google_sub == "sub-5"
        assert result.google_email == "ada@g.com"
        assert result.google_linked_at is not None

    @pytest.mark.asyncio
    async def test_refuses_when_linked_to_a_different_user(self) -> None:
        svc = self._make_svc()
        other_user = make_user(email="other@example.com")
        svc._user_repo.get_by_google_sub.return_value = other_user
        user = make_user(email="me@example.com")

        with pytest.raises(GoogleAccountAlreadyLinkedError):
            await svc.link_google(user=user, google_sub="sub-6", google_email="ada@g.com")

    @pytest.mark.asyncio
    async def test_relinking_same_user_is_a_noop_conflict(self) -> None:
        svc = self._make_svc()
        user = make_user()
        svc._user_repo.get_by_google_sub.return_value = user

        result = await svc.link_google(user=user, google_sub="sub-7", google_email="ada@g.com")
        assert result.google_sub == "sub-7"


class TestUnlinkGoogle:
    def _make_svc(self) -> AuthService:
        return AuthService(AsyncMock(), _google_settings())

    @pytest.mark.asyncio
    async def test_unlinks_when_password_set(self) -> None:
        svc = self._make_svc()
        user = make_user(password_hash="hashed")
        user.google_sub = "sub-8"
        user.google_email = "ada@g.com"

        result = await svc.unlink_google(user=user)

        assert result.google_sub is None
        assert result.google_email is None
        assert result.google_linked_at is None

    @pytest.mark.asyncio
    async def test_refuses_when_no_password_set(self) -> None:
        svc = self._make_svc()
        user = make_user(password_hash=None)
        user.google_sub = "sub-9"

        with pytest.raises(LastAuthMethodError):
            await svc.unlink_google(user=user)


# ══════════════════════════════════════════════════════════════════════════════
# API layer
# ══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def app() -> Any:
    from app.main import app as fastapi_app

    return fastapi_app


def _override_settings_and_db(app: Any, settings: Settings | None = None) -> None:
    from app.api.deps import get_db
    from app.config.settings import get_settings

    async def mock_get_db() -> Any:
        yield AsyncMock()

    app.dependency_overrides[get_settings] = lambda: settings or _google_settings()
    app.dependency_overrides[get_db] = mock_get_db


def _override_current_user(app: Any, user: User) -> None:
    from app.auth.dependencies import get_current_user

    async def mock_get_user() -> User:
        return user

    app.dependency_overrides[get_current_user] = mock_get_user


class TestGoogleStartEndpoint:
    @pytest.mark.asyncio
    async def test_503_when_not_configured(self, app: Any) -> None:
        _override_settings_and_db(app, settings=_test_settings())
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get("/v1/auth/google/start", follow_redirects=False)
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_redirects_to_google_with_state_cookie(self, app: Any) -> None:
        _override_settings_and_db(app)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get("/v1/auth/google/start", follow_redirects=False)
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 302
        assert "accounts.google.com" in resp.headers["location"]
        assert google_oauth.OAUTH_STATE_COOKIE in resp.cookies


class TestGoogleLinkStartEndpoint:
    @pytest.mark.asyncio
    async def test_requires_authentication(self, app: Any) -> None:
        _override_settings_and_db(app)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.post("/v1/auth/google/link")
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_returns_authorize_url_and_sets_cookie(self, app: Any) -> None:
        _override_settings_and_db(app)
        user = make_user()
        _override_current_user(app, user)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.post("/v1/auth/google/link")
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 200
        assert "accounts.google.com" in resp.json()["authorize_url"]
        assert google_oauth.OAUTH_STATE_COOKIE in resp.cookies


class TestGoogleCallbackEndpoint:
    @pytest.mark.asyncio
    async def test_google_denied_redirects_to_login_with_error(self, app: Any) -> None:
        _override_settings_and_db(app)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/v1/auth/google/callback",
                    params={"error": "access_denied"},
                    follow_redirects=False,
                )
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 302
        assert "google_error=google_denied" in resp.headers["location"]

    @pytest.mark.asyncio
    async def test_missing_state_cookie_redirects_with_invalid_state(self, app: Any) -> None:
        settings = _google_settings()
        _override_settings_and_db(app, settings=settings)
        state_token, _ = google_oauth.encode_oauth_state(
            mode="login", redirect_path="/", settings=settings
        )
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/v1/auth/google/callback",
                    params={"code": "c", "state": state_token},
                    follow_redirects=False,
                )
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 302
        assert "google_error=invalid_state" in resp.headers["location"]

    @pytest.mark.asyncio
    async def test_state_cookie_mismatch_redirects_with_invalid_state(self, app: Any) -> None:
        settings = _google_settings()
        _override_settings_and_db(app, settings=settings)
        state_token, _ = google_oauth.encode_oauth_state(
            mode="login", redirect_path="/", settings=settings
        )
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                ac.cookies.set(google_oauth.OAUTH_STATE_COOKIE, "different-token")
                resp = await ac.get(
                    "/v1/auth/google/callback",
                    params={"code": "c", "state": state_token},
                    follow_redirects=False,
                )
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 302
        assert "google_error=invalid_state" in resp.headers["location"]

    @pytest.mark.asyncio
    async def test_successful_new_user_login_redirects_to_onboarding_with_session(
        self, app: Any
    ) -> None:
        settings = _google_settings()
        _override_settings_and_db(app, settings=settings)
        state_token, flow = google_oauth.encode_oauth_state(
            mode="login", redirect_path="/", settings=settings
        )
        id_token = _make_id_token(nonce=flow.nonce, sub="new-sub", email="brand-new@example.com")

        fake_pair = TokenPair(access_token="access", refresh_token="refresh", expires_in=1800)
        fake_org = make_org(name="Brand New's Workspace")
        fake_user = make_user(email="brand-new@example.com")
        fake_user.id = uuid.uuid4()

        try:
            with (
                patch("app.api.v1.auth.google_oauth.exchange_code_for_tokens") as mock_exchange,
                patch("app.api.v1.auth.google_oauth.verify_google_id_token") as mock_verify,
                patch("app.api.v1.auth.AuthService") as mock_svc_cls,
            ):
                mock_exchange.return_value = {"id_token": id_token}
                mock_verify.return_value = GoogleIdentity(
                    sub="new-sub",
                    email="brand-new@example.com",
                    display_name="Brand New",
                    avatar_url=None,
                )
                mock_svc_cls.return_value.login_or_register_with_google = AsyncMock(
                    return_value=(fake_pair, fake_user, fake_org, True)
                )
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    ac.cookies.set(google_oauth.OAUTH_STATE_COOKIE, state_token)
                    resp = await ac.get(
                        "/v1/auth/google/callback",
                        params={"code": "auth-code", "state": state_token},
                        follow_redirects=False,
                    )
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 302
        location = resp.headers["location"]
        assert location.startswith("https://app.test.costorah.com/onboarding#session=")
        fragment = location.split("#session=", 1)[1]
        import urllib.parse as up

        decoded = json.loads(base64.b64decode(up.unquote(fragment)))
        assert decoded["access_token"] == "access"
        assert decoded["workspace"]["name"] == "Brand New's Workspace"
        assert "costorah_access_token" in resp.cookies

    @pytest.mark.asyncio
    async def test_successful_existing_user_login_redirects_to_root(self, app: Any) -> None:
        settings = _google_settings()
        _override_settings_and_db(app, settings=settings)
        state_token, flow = google_oauth.encode_oauth_state(
            mode="login", redirect_path="/", settings=settings
        )
        id_token = _make_id_token(nonce=flow.nonce)

        fake_pair = TokenPair(access_token="access", refresh_token="refresh", expires_in=1800)
        fake_user = make_user()

        try:
            with (
                patch("app.api.v1.auth.google_oauth.exchange_code_for_tokens") as mock_exchange,
                patch("app.api.v1.auth.google_oauth.verify_google_id_token") as mock_verify,
                patch("app.api.v1.auth.AuthService") as mock_svc_cls,
            ):
                mock_exchange.return_value = {"id_token": id_token}
                mock_verify.return_value = GoogleIdentity(
                    sub="sub-x", email=fake_user.email, display_name="Ada", avatar_url=None
                )
                mock_svc_cls.return_value.login_or_register_with_google = AsyncMock(
                    return_value=(fake_pair, fake_user, None, False)
                )
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    ac.cookies.set(google_oauth.OAUTH_STATE_COOKIE, state_token)
                    resp = await ac.get(
                        "/v1/auth/google/callback",
                        params={"code": "auth-code", "state": state_token},
                        follow_redirects=False,
                    )
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 302
        assert resp.headers["location"].startswith("https://app.test.costorah.com/#session=")

    @pytest.mark.asyncio
    async def test_invalid_id_token_redirects_with_invalid_token_error(self, app: Any) -> None:
        settings = _google_settings()
        _override_settings_and_db(app, settings=settings)
        state_token, _flow = google_oauth.encode_oauth_state(
            mode="login", redirect_path="/", settings=settings
        )
        try:
            with (
                patch("app.api.v1.auth.google_oauth.exchange_code_for_tokens") as mock_exchange,
                patch("app.api.v1.auth.google_oauth.verify_google_id_token") as mock_verify,
            ):
                mock_exchange.return_value = {"id_token": "whatever"}
                mock_verify.side_effect = InvalidGoogleTokenError("bad token")
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    ac.cookies.set(google_oauth.OAUTH_STATE_COOKIE, state_token)
                    resp = await ac.get(
                        "/v1/auth/google/callback",
                        params={"code": "auth-code", "state": state_token},
                        follow_redirects=False,
                    )
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 302
        assert "google_error=invalid_token" in resp.headers["location"]

    @pytest.mark.asyncio
    async def test_link_mode_success_redirects_to_settings(self, app: Any) -> None:
        settings = _google_settings()
        _override_settings_and_db(app, settings=settings)
        target_user_id = uuid.uuid4()
        state_token, flow = google_oauth.encode_oauth_state(
            mode="link",
            redirect_path="/settings",
            settings=settings,
            user_id=str(target_user_id),
        )
        id_token = _make_id_token(nonce=flow.nonce)
        target_user = make_user()
        target_user.id = target_user_id

        try:
            with (
                patch("app.api.v1.auth.google_oauth.exchange_code_for_tokens") as mock_exchange,
                patch("app.api.v1.auth.google_oauth.verify_google_id_token") as mock_verify,
                patch("app.api.v1.auth.AuthService") as mock_svc_cls,
            ):
                mock_exchange.return_value = {"id_token": id_token}
                mock_verify.return_value = GoogleIdentity(
                    sub="link-sub", email="ada@example.com", display_name="Ada", avatar_url=None
                )
                mock_svc_cls.return_value.get_by_id = AsyncMock(return_value=target_user)
                mock_svc_cls.return_value.link_google = AsyncMock(return_value=target_user)
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    ac.cookies.set(google_oauth.OAUTH_STATE_COOKIE, state_token)
                    resp = await ac.get(
                        "/v1/auth/google/callback",
                        params={"code": "auth-code", "state": state_token},
                        follow_redirects=False,
                    )
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 302
        assert resp.headers["location"] == "https://app.test.costorah.com/settings?google_linked=1"

    @pytest.mark.asyncio
    async def test_link_mode_already_linked_redirects_with_error(self, app: Any) -> None:
        settings = _google_settings()
        _override_settings_and_db(app, settings=settings)
        target_user_id = uuid.uuid4()
        state_token, flow = google_oauth.encode_oauth_state(
            mode="link",
            redirect_path="/settings",
            settings=settings,
            user_id=str(target_user_id),
        )
        id_token = _make_id_token(nonce=flow.nonce)
        target_user = make_user()
        target_user.id = target_user_id

        try:
            with (
                patch("app.api.v1.auth.google_oauth.exchange_code_for_tokens") as mock_exchange,
                patch("app.api.v1.auth.google_oauth.verify_google_id_token") as mock_verify,
                patch("app.api.v1.auth.AuthService") as mock_svc_cls,
            ):
                mock_exchange.return_value = {"id_token": id_token}
                mock_verify.return_value = GoogleIdentity(
                    sub="link-sub", email="ada@example.com", display_name="Ada", avatar_url=None
                )
                mock_svc_cls.return_value.get_by_id = AsyncMock(return_value=target_user)
                mock_svc_cls.return_value.link_google = AsyncMock(
                    side_effect=GoogleAccountAlreadyLinkedError
                )
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    ac.cookies.set(google_oauth.OAUTH_STATE_COOKIE, state_token)
                    resp = await ac.get(
                        "/v1/auth/google/callback",
                        params={"code": "auth-code", "state": state_token},
                        follow_redirects=False,
                    )
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 302
        assert "google_error=already_linked" in resp.headers["location"]

    @pytest.mark.asyncio
    async def test_replaying_the_same_state_twice_fails_the_second_time_by_ttl_not_reuse(
        self, app: Any
    ) -> None:
        """The state JWT itself has no server-side one-time-use tracking (see
        google_oauth.py's module docstring) — replay protection for the
        *code* itself comes from Google's own one-time authorization code
        semantics (a second exchange attempt fails at Google's token
        endpoint). This test only pins that a well-formed, still-valid
        state can be decoded more than once (by design, not a bug) while an
        expired one cannot (covered by TestOAuthState.test_expired_token_is_rejected).
        """
        settings = _google_settings()
        state_token, _ = google_oauth.encode_oauth_state(
            mode="login", redirect_path="/", settings=settings
        )
        first = google_oauth.decode_oauth_state(state_token, settings=settings)
        second = google_oauth.decode_oauth_state(state_token, settings=settings)
        assert first.nonce == second.nonce


class TestGoogleUnlinkEndpoint:
    @pytest.mark.asyncio
    async def test_requires_authentication(self, app: Any) -> None:
        _override_settings_and_db(app)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.post("/v1/auth/google/unlink")
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_success_returns_updated_user(self, app: Any) -> None:
        _override_settings_and_db(app)
        user = make_user(password_hash="hashed")
        user.google_sub = "sub-1"
        _override_current_user(app, user)
        unlinked_user = make_user(password_hash="hashed")
        unlinked_user.id = user.id
        unlinked_user.google_sub = None
        try:
            with patch("app.api.v1.auth.AuthService") as mock_svc_cls:
                mock_svc_cls.return_value.unlink_google = AsyncMock(return_value=unlinked_user)
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post("/v1/auth/google/unlink")
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 200
        assert resp.json()["google_linked"] is False

    @pytest.mark.asyncio
    async def test_refuses_when_last_auth_method(self, app: Any) -> None:
        _override_settings_and_db(app)
        user = make_user(password_hash=None)
        _override_current_user(app, user)
        try:
            with patch("app.api.v1.auth.AuthService") as mock_svc_cls:
                mock_svc_cls.return_value.unlink_google = AsyncMock(side_effect=LastAuthMethodError)
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post("/v1/auth/google/unlink")
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 400
