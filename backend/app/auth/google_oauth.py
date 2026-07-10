"""Google OAuth 2.0 / OpenID Connect — EP-24.5.

Authorization Code flow with PKCE, not the Google-Identity-Services
ID-token-only button — Part 9 of this EP names "OAuth state validation",
"CSRF protection", and "nonce validation" as explicit requirements, which
describe the classic redirect-based flow, not a bare ID-token POST.

Everything downstream of a validated Google identity (session issuance,
account creation, linking) belongs to ``AuthService`` — this module owns
exactly the OAuth/OIDC mechanics: building the authorize URL, exchanging an
authorization code for tokens, and verifying the returned ID token. It never
touches the database and never issues a Costorah session itself.

State/CSRF design (no server-side session store — consistent with this
codebase's "avoid new stateful storage when a signed token suffices"
convention, e.g. app/auth/tokens.py's refresh tokens):

* The OAuth ``state`` parameter IS a short-lived HS256 JWT (signed with the
  same ``settings.jwt_secret`` app/auth/tokens.py already uses), encoding a
  random CSRF id, the OIDC ``nonce``, the PKCE ``code_verifier``, the flow
  ``mode`` ("login" | "link"), and — for "link" only — the already-
  authenticated user's id.
* The identical JWT is also set as a short-lived, httpOnly, host-only
  (no ``domain=`` attribute — deliberately distinct from the cross-subdomain
  session cookies in app/auth/cookies.py) ``SameSite=Lax`` cookie at flow
  start. ``/google/start`` and ``/google/callback`` are always same-origin
  (both are backend routes), so this cookie round-trips correctly through
  Google's redirect regardless of which frontend domain initiated the flow.
* The callback must see the cookie and the query-param ``state`` match
  (constant-time comparison) *and* the JWT itself must still verify — this
  is the standard double-submit-cookie CSRF pattern, with the "double
  submit" value being a signed token instead of a bare random string so it
  is also tamper-evident and self-expiring (10 minutes).
* For the "link" mode, the state additionally embeds the initiating user's
  id — since ``/google/link`` requires an authenticated caller
  (``CurrentUser``) before it will ever mint one, an attacker cannot obtain
  a validly-signed "link" state for a victim's account without already
  holding the victim's access token, which is a strictly stronger guarantee
  than the cookie check alone.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

import httpx
import jwt
from jwt import PyJWKClient

from app.config.settings import Settings
from app.http.transport import HttpTransport, HttpxTransport

GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 - not a secret, an endpoint
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = frozenset({"https://accounts.google.com", "accounts.google.com"})

OAUTH_STATE_COOKIE = "costorah_oauth_state"
STATE_TTL_MINUTES = 10

_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(GOOGLE_JWKS_URL)
    return _jwks_client


class SigningKeyResolver(Protocol):
    """Resolves the RSA public key that signed a given Google ID token.

    Matches ``jwt.PyJWKClient``'s relevant surface (``get_signing_key_from_jwt``
    returning an object with a ``.key`` attribute). Injectable so tests can
    supply a real RSA keypair-signed token without a network JWKS fetch.
    """

    def get_signing_key_from_jwt(self, token: str) -> Any: ...  # noqa: ANN401


class GoogleOAuthError(Exception):
    """Base class for Google OAuth flow failures."""


class GoogleOAuthNotConfiguredError(GoogleOAuthError):
    """Google OAuth credentials are not configured on this deployment."""


class OAuthStateError(GoogleOAuthError):
    """The `state` cookie/query-param pair is missing, mismatched, or invalid."""


class GoogleTokenExchangeError(GoogleOAuthError):
    """Google's token endpoint rejected the authorization code."""


class InvalidGoogleTokenError(GoogleOAuthError):
    """The Google ID token failed signature, issuer, audience, expiry, or nonce validation."""


@dataclass(frozen=True, slots=True)
class PkcePair:
    verifier: str
    challenge: str


@dataclass(frozen=True, slots=True)
class GoogleIdentity:
    """The minimal, already-validated identity fields this platform stores (Part 9)."""

    sub: str
    email: str
    display_name: str
    avatar_url: str | None


@dataclass(frozen=True, slots=True)
class OAuthFlowState:
    csrf_id: str
    nonce: str
    code_verifier: str
    mode: str  # "login" | "link"
    redirect_path: str
    user_id: str | None


def pkce_challenge_from_verifier(verifier: str) -> str:
    """Derive the S256 PKCE code_challenge for a given verifier."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def generate_pkce_pair() -> PkcePair:
    """Return a random PKCE verifier + its S256 challenge."""
    verifier = secrets.token_urlsafe(64)[:128]
    return PkcePair(verifier=verifier, challenge=pkce_challenge_from_verifier(verifier))


def encode_oauth_state(
    *,
    mode: str,
    redirect_path: str,
    settings: Settings,
    user_id: str | None = None,
) -> tuple[str, OAuthFlowState]:
    """Build a new signed OAuth state JWT plus the flow values it encodes."""
    now = datetime.now(UTC)
    flow = OAuthFlowState(
        csrf_id=secrets.token_urlsafe(24),
        nonce=secrets.token_urlsafe(24),
        code_verifier=generate_pkce_pair().verifier,
        mode=mode,
        redirect_path=redirect_path,
        user_id=user_id,
    )
    payload: dict[str, Any] = {
        "csrf_id": flow.csrf_id,
        "nonce": flow.nonce,
        "code_verifier": flow.code_verifier,
        "mode": flow.mode,
        "redirect_path": flow.redirect_path,
        "user_id": flow.user_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=STATE_TTL_MINUTES)).timestamp()),
    }
    token = jwt.encode(
        payload, settings.jwt_secret.get_secret_value(), algorithm=settings.jwt_algorithm
    )
    return token, flow


def decode_oauth_state(token: str, *, settings: Settings) -> OAuthFlowState:
    """Validate signature + expiry and return the encoded flow values.

    Raises ``OAuthStateError`` on any structural or cryptographic failure —
    never distinguishes "expired" from "forged" from "malformed" to a caller.
    """
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            leeway=30,
            options={"require": ["exp", "iat", "csrf_id", "nonce", "code_verifier", "mode"]},
        )
    except jwt.exceptions.InvalidTokenError as exc:
        raise OAuthStateError("Invalid or expired OAuth state") from exc

    return OAuthFlowState(
        csrf_id=payload["csrf_id"],
        nonce=payload["nonce"],
        code_verifier=payload["code_verifier"],
        mode=payload["mode"],
        redirect_path=payload.get("redirect_path", "/"),
        user_id=payload.get("user_id"),
    )


def verify_state_match(*, cookie_value: str | None, query_value: str | None) -> None:
    """Constant-time-compare the state cookie against the callback's `state` param."""
    if not cookie_value or not query_value:
        raise OAuthStateError("Missing OAuth state")
    if not secrets.compare_digest(cookie_value, query_value):
        raise OAuthStateError("OAuth state mismatch")


def build_authorize_url(
    *,
    settings: Settings,
    redirect_uri: str,
    state: str,
    nonce: str,
    code_challenge: str,
    login_hint: str | None = None,
) -> str:
    """Build Google's OAuth 2.0 authorization endpoint URL for this flow."""
    if not settings.google_client_id:
        raise GoogleOAuthNotConfiguredError("Google OAuth is not configured")

    params: dict[str, str] = {
        "client_id": settings.google_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "access_type": "online",
        "prompt": "select_account",
    }
    if login_hint:
        params["login_hint"] = login_hint
    return str(httpx.URL(GOOGLE_AUTHORIZE_URL, params=params))


async def exchange_code_for_tokens(
    *,
    settings: Settings,
    code: str,
    redirect_uri: str,
    code_verifier: str,
    transport: HttpTransport | None = None,
) -> dict[str, Any]:
    """Exchange an authorization code for Google's token response (contains `id_token`).

    Never logs the request/response body — both may carry token material.
    """
    if not settings.google_client_id or not settings.google_client_secret:
        raise GoogleOAuthNotConfiguredError("Google OAuth is not configured")

    own_transport = transport is None
    t = transport or HttpxTransport()
    try:
        response = await t.request(
            "POST",
            GOOGLE_TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret.get_secret_value(),
                "code": code,
                "code_verifier": code_verifier,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            },
        )
    except httpx.HTTPError as exc:
        raise GoogleTokenExchangeError("Could not reach Google's token endpoint") from exc
    finally:
        if own_transport:
            await t.aclose()

    if response.status_code != 200:
        raise GoogleTokenExchangeError("Google rejected the authorization code")

    body: dict[str, Any] = response.json()
    if "id_token" not in body:
        raise GoogleTokenExchangeError("Google's token response did not include an ID token")
    return body


def verify_google_id_token(
    *,
    id_token: str,
    settings: Settings,
    expected_nonce: str,
    signing_key_resolver: SigningKeyResolver | None = None,
) -> GoogleIdentity:
    """Verify a Google ID token's signature, issuer, audience, expiry, and nonce.

    Never trusts client-supplied claims without this full verification
    (Part 1: "Do not trust client-side data") — this is the only place in
    the codebase that turns a raw Google ID token into a ``GoogleIdentity``.
    """
    if not settings.google_client_id:
        raise GoogleOAuthNotConfiguredError("Google OAuth is not configured")

    resolver = signing_key_resolver or _get_jwks_client()
    try:
        signing_key = resolver.get_signing_key_from_jwt(id_token)
    except Exception as exc:
        raise InvalidGoogleTokenError("Could not resolve Google's signing key") from exc

    try:
        claims: dict[str, Any] = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.google_client_id,
            options={"require": ["exp", "iat", "sub", "aud", "iss", "email"]},
        )
    except jwt.exceptions.InvalidTokenError as exc:
        raise InvalidGoogleTokenError("Google ID token failed validation") from exc

    if claims.get("iss") not in GOOGLE_ISSUERS:
        raise InvalidGoogleTokenError("Unexpected token issuer")

    token_nonce = claims.get("nonce")
    if not token_nonce or not secrets.compare_digest(str(token_nonce), expected_nonce):
        raise InvalidGoogleTokenError("Nonce mismatch")

    email = claims.get("email")
    if not email:
        raise InvalidGoogleTokenError("Google ID token has no email claim")
    if not claims.get("email_verified", False):
        raise InvalidGoogleTokenError("Google account email is not verified")

    sub = claims.get("sub")
    if not sub:
        raise InvalidGoogleTokenError("Google ID token has no subject claim")

    return GoogleIdentity(
        sub=str(sub),
        email=str(email),
        display_name=str(claims.get("name") or email.split("@")[0]),
        avatar_url=claims.get("picture"),
    )


def parse_user_id(raw: str | None) -> uuid.UUID | None:
    if raw is None:
        return None
    return uuid.UUID(raw)


__all__ = [
    "GOOGLE_AUTHORIZE_URL",
    "GOOGLE_ISSUERS",
    "GOOGLE_JWKS_URL",
    "GOOGLE_TOKEN_URL",
    "OAUTH_STATE_COOKIE",
    "STATE_TTL_MINUTES",
    "GoogleIdentity",
    "GoogleOAuthError",
    "GoogleOAuthNotConfiguredError",
    "GoogleTokenExchangeError",
    "InvalidGoogleTokenError",
    "OAuthFlowState",
    "OAuthStateError",
    "PkcePair",
    "SigningKeyResolver",
    "build_authorize_url",
    "decode_oauth_state",
    "encode_oauth_state",
    "exchange_code_for_tokens",
    "generate_pkce_pair",
    "parse_user_id",
    "pkce_challenge_from_verifier",
    "verify_google_id_token",
    "verify_state_match",
]
