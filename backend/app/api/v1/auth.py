"""Authentication API — EP-05 / F-017, extended by EP-21.2, EP-24.4, EP-24.6.1.

Endpoints:
  POST /v1/auth/register             — create a User + personal workspace (EP-24.6.1: no
                                        session — verify the email, then log in)
  POST /v1/auth/login                — issue access + refresh tokens
  POST /v1/auth/logout               — revoke the current session
  POST /v1/auth/refresh              — rotate refresh token, issue new access token
  GET  /v1/auth/me                   — the authenticated caller's profile
  POST /v1/auth/onboarding/complete  — mark the first-time onboarding wizard done (EP-21.3)
  POST /v1/auth/verify-email         — consume an email verification token (JSON body)
  GET  /v1/auth/verify-email         — same, as a plain link-click URL (EP-24.4)
  POST /v1/auth/resend-verification  — re-send the verification email, rate-limited (EP-24.4)
  POST /v1/auth/forgot-password      — request a password-reset email, rate-limited (EP-24.4)
  POST /v1/auth/request-password-reset — pre-EP-24.4 alias of /forgot-password, kept mounted
  POST /v1/auth/reset-password       — consume a reset token and set a new password
  GET  /v1/auth/google/start         — begin "Continue with Google" login/registration (EP-24.5)
  POST /v1/auth/google/link          — begin linking Google to the authenticated account (EP-24.5)
  GET  /v1/auth/google/callback      — Google's OAuth redirect target (EP-24.5)
  POST /v1/auth/google/unlink        — unlink Google from the authenticated account (EP-24.5)
  POST /v1/auth/set-password         — first password for a Google-only account (EP-24.6.1)

Google OAuth (EP-24.5): Authorization Code + PKCE, reusing this same
AuthService/session-issuance/cookie machinery — see CLAUDE.md's EP-24.5
section and app/auth/google_oauth.py's module docstring for the full
state/CSRF/nonce design. 503s cleanly (never crashes) when
`settings.google_oauth_configured` is False.

Session cookies (EP-21.2): login, register, and refresh additionally set
httpOnly `costorah_access_token`/`costorah_refresh_token` cookies
(app.auth.cookies) alongside the unchanged JSON token response — existing
bearer-token clients (apps/dashboard) are unaffected; apps/website relies
on the cookie. logout clears both cookies.

Transactional email (EP-24.4): registration, resend-verification, and
forgot/reset-password all send real email via `app.email.service.EmailService`
(Resend in production) — see CLAUDE.md's EP-24.4 section for the full
architecture. Every one of these endpoints keeps working, response shape
unchanged, in any environment without `RESEND_API_KEY` configured (local
dev, CI) — `EmailService` degrades to a logged no-op send in that case.
"""

from __future__ import annotations

import base64
import json
import uuid
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse
from jwt.exceptions import DecodeError, ExpiredSignatureError, InvalidTokenError

from app.api.deps import DbDep, SettingsDep
from app.auth import google_oauth
from app.auth.audit import AuditEvent, log_auth_event
from app.auth.cookies import ACCESS_TOKEN_COOKIE, clear_session_cookies, set_session_cookies
from app.auth.dependencies import CurrentUser
from app.auth.exceptions import (
    AccountDisabledError,
    EmailAlreadyRegisteredError,
    EmailAlreadyVerifiedError,
    EmailNotVerifiedError,
    GoogleAccountAlreadyLinkedError,
    InvalidCredentialsError,
    LastAuthMethodError,
    NoPersonalWorkspaceError,
    OwnerOfSharedWorkspaceError,
    PasswordAlreadyConfiguredError,
    UsernameAlreadyTakenError,
)
from app.auth.exceptions import InvalidTokenError as AuthInvalidTokenError
from app.auth.rate_limit import EmailRateLimiter, LoginRateLimiter
from app.auth.service import AuthService, TokenPair
from app.auth.tokens import decode_access_token
from app.config.settings import Settings
from app.models.organization import Organization
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    DeleteAccountRequest,
    LoginRequest,
    LoginResponse,
    MessageResponse,
    PasswordResetRequest,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    ResendVerificationRequest,
    ResetPasswordRequest,
    SetPasswordRequest,
    TokenResponse,
    UpdatePreferencesRequest,
    UpdateProfileRequest,
    UpgradeToBusinessRequest,
    UserPublic,
    VerifyEmailRequest,
    WorkspacePublic,
)

router = APIRouter(prefix="/auth", tags=["authentication"])


def _get_login_rate_limiter(request: Request) -> LoginRateLimiter:
    """Return the app-wide login rate limiter (lazily created, Redis-backed).

    Stored on app.state so the sliding windows and lockout counters are shared
    across requests within a worker; Redis (when reachable) shares them across
    all workers.
    """
    limiter = getattr(request.app.state, "login_rate_limiter", None)
    if limiter is None:
        container = getattr(request.app.state, "container", None)
        limiter = LoginRateLimiter(redis=getattr(container, "redis", None))
        request.app.state.login_rate_limiter = limiter
    return limiter


def _get_email_rate_limiter(request: Request) -> EmailRateLimiter:
    """Return the app-wide verification/reset email rate limiter (EP-24.4).

    Same lazily-created, app.state-cached, Redis-backed pattern as
    ``_get_login_rate_limiter`` above — a second limiter instance because
    the policy (a single sliding window, no lockout) genuinely differs
    from login's, not because the underlying mechanism does.
    """
    limiter = getattr(request.app.state, "email_rate_limiter", None)
    if limiter is None:
        container = getattr(request.app.state, "container", None)
        limiter = EmailRateLimiter(redis=getattr(container, "redis", None))
        request.app.state.email_rate_limiter = limiter
    return limiter


def _build_user_public(user: Any) -> UserPublic:  # noqa: ANN401
    return UserPublic(
        id=user.external_id,
        email=user.email,
        username=user.username,
        display_name=user.display_name,
        status=user.status,
        email_verified=user.email_verified,
        onboarding_completed=user.onboarding_completed_at is not None,
        avatar_url=user.avatar_url,
        bio=user.bio,
        timezone=user.timezone,
        created_at=user.created_at,
        preferences=user.preferences,
        google_linked=user.google_sub is not None,
        google_email=user.google_email,
        last_login_provider=user.last_login_provider,
        password_configured=user.password_hash is not None,
    )


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account and personal workspace; verification required before login",
    description=(
        "EP-24.6.1: does NOT issue a session. Creates the User (email_verified=False) "
        "and its personal workspace, sends a verification email, and returns them with "
        "no token pair — `email_verification_required` is always true for this path. "
        "The account can only obtain a session afterwards via POST /v1/auth/login, "
        "which itself refuses to issue one until the email is verified."
    ),
)
async def register(
    body: RegisterRequest,
    request: Request,
    db: DbDep,
    settings: SettingsDep,
) -> RegisterResponse:
    svc = AuthService(db, settings)
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    try:
        _pair, user, workspace = await svc.register(
            email=body.email,
            password=body.password,
            display_name=body.display_name,
            account_type=body.account_type,
            organization_name=body.organization_name,
            ip_address=ip,
            user_agent=ua,
        )
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        ) from exc

    # No session cookies are set here (EP-24.6.1) — `_pair` is always None
    # for this path; `register()`'s own docstring explains why.
    return RegisterResponse(
        email_verification_required=True,
        user=_build_user_public(user),
        workspace=WorkspacePublic(
            # EP-25.3: the raw hyphenated UUID, not `workspace.external_id`
            # (`org_<hex>`) — every organization_id-typed endpoint in this
            # API (query param or path param) declares `uuid.UUID`, matching
            # `OrgMembershipItem.id`'s own documented convention
            # ("organization UUID (hyphenated) — consumed directly by
            # dashboard endpoints"). Using external_id here was the root
            # cause of budget/alert/analytics/dashboard creation 422s for
            # every Google OAuth login/registration — see CLAUDE.md's
            # EP-25.3 section for the full trace.
            id=str(workspace.id),
            name=workspace.name,
            slug=workspace.slug,
            is_personal=workspace.is_personal,
        ),
    )


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Authenticate with email and password",
)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: DbDep,
    settings: SettingsDep,
) -> LoginResponse:
    svc = AuthService(db, settings)
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    limiter = _get_login_rate_limiter(request)
    decision = await limiter.check(ip=ip, email=body.email)
    if not decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again later.",
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )

    try:
        pair, user = await svc.login(
            email=body.email,
            password=body.password,
            ip_address=ip,
            user_agent=ua,
        )
    except InvalidCredentialsError as exc:
        await limiter.record_failure(email=body.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except AccountDisabledError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been disabled",
        ) from exc
    except EmailNotVerifiedError as exc:
        # EP-24.4.1: the credentials were correct — this is deliberately
        # not counted as a rate-limiter failure (that's reserved for wrong
        # passwords), so a legitimate user waiting on their verification
        # email can retry login without tripping a lockout.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email before signing in.",
        ) from exc
    await limiter.record_success(email=body.email)
    set_session_cookies(response, pair, settings)
    return LoginResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        token_type="bearer",  # noqa: S106
        expires_in=pair.expires_in,
        user=_build_user_public(user),
    )


@router.get(
    "/me",
    response_model=UserPublic,
    summary="The authenticated caller's profile",
)
async def me(current_user: CurrentUser) -> UserPublic:
    return _build_user_public(current_user)


def _current_session_id(request: Request, settings: SettingsDep) -> uuid.UUID | None:
    """Best-effort extraction of the calling session's id from its own access token.

    Mirrors ``logout``'s token-location logic (header, then cookie). Used by
    change-password to know which session to spare when revoking the rest —
    if the token can't be read for any reason, callers treat that as "no
    session to spare" and revoke everything, which is still safe.
    """
    auth_header = request.headers.get("authorization", "")
    raw_token: str | None
    if auth_header.lower().startswith("bearer "):
        raw_token = auth_header[7:].strip()
    else:
        raw_token = request.cookies.get(ACCESS_TOKEN_COOKIE)
    if not raw_token:
        return None
    try:
        claims = decode_access_token(raw_token, settings=settings)
    except (ExpiredSignatureError, DecodeError, InvalidTokenError):
        return None
    session_id_str = claims.get("jti")
    if not isinstance(session_id_str, str):
        return None
    try:
        return uuid.UUID(session_id_str)
    except ValueError:
        return None


@router.patch(
    "/me",
    response_model=UserPublic,
    summary="Update the authenticated caller's profile",
    description=(
        "Partial update (EP-22.2) — only the fields present in the request "
        "body are applied; omitted fields are left unchanged."
    ),
)
async def update_profile(
    body: UpdateProfileRequest,
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
) -> UserPublic:
    svc = AuthService(db, settings)
    try:
        user = await svc.update_profile(
            user=current_user,
            display_name=body.display_name,
            username=body.username,
            avatar_url=body.avatar_url,
            bio=body.bio,
            timezone=body.timezone,
            set_fields=body.model_fields_set,
        )
    except UsernameAlreadyTakenError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This username is already taken",
        ) from exc
    return _build_user_public(user)


@router.patch(
    "/me/preferences",
    response_model=UserPublic,
    summary="Merge a patch into the authenticated caller's preferences",
    description=(
        "Shallow-merges the given keys into the stored preferences JSON "
        "(theme, timezone, currency, date format, sidebar-collapsed, "
        "notification toggles, ...). Keys not present in the request are "
        "left untouched."
    ),
)
async def update_preferences(
    body: UpdatePreferencesRequest,
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
) -> UserPublic:
    svc = AuthService(db, settings)
    user = await svc.update_preferences(user=current_user, patch=body.preferences)
    return _build_user_public(user)


@router.post(
    "/change-password",
    response_model=MessageResponse,
    summary="Change the authenticated caller's password",
    description=(
        "Requires the current password. On success, every other active "
        "session for this user is revoked — the session making this "
        "request stays signed in."
    ),
)
async def change_password(
    body: ChangePasswordRequest,
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    request: Request,
) -> MessageResponse:
    svc = AuthService(db, settings)
    session_id = _current_session_id(request, settings)
    try:
        await svc.change_password(
            user=current_user,
            current_password=body.current_password,
            new_password=body.new_password,
            current_session_id=session_id or uuid.uuid4(),
        )
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        ) from exc
    return MessageResponse(message="Password changed successfully")


@router.post(
    "/set-password",
    response_model=UserPublic,
    summary="Set the first password for a Google-only account (EP-24.6.1)",
    description=(
        "For an account with no password yet (`password_configured: false` on "
        "UserPublic — i.e. registered via Google). Refuses with 409 if a password "
        "is already set; use /change-password for that account instead."
    ),
)
async def set_password(
    body: SetPasswordRequest,
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
) -> UserPublic:
    svc = AuthService(db, settings)
    try:
        await svc.set_password(user=current_user, new_password=body.new_password)
    except PasswordAlreadyConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A password is already set for this account — use change-password instead",
        ) from exc
    return _build_user_public(current_user)


@router.post(
    "/upgrade-to-business",
    response_model=WorkspacePublic,
    summary="Convert the caller's personal workspace into a Business workspace (EP-25.2)",
    description=(
        "Reuses the existing personal Organization row (same id, same "
        "projects/provider connections/budgets/alerts/API keys) — flips "
        "`is_personal` to False and optionally renames it (default 'My "
        "Team' if no name is supplied). No new organization is created, no "
        "data is migrated, no logout is required. Members/Invitations/RBAC/"
        "Workspace Settings/the workspace switcher are enabled immediately "
        "for the returned workspace, driven entirely by `is_personal` — the "
        "same field the frontend already reads."
    ),
)
async def upgrade_to_business(
    body: UpgradeToBusinessRequest,
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
) -> WorkspacePublic:
    svc = AuthService(db, settings)
    try:
        workspace = await svc.upgrade_to_business(
            user=current_user, organization_name=body.organization_name
        )
    except NoPersonalWorkspaceError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No personal workspace found to upgrade",
        ) from exc
    return WorkspacePublic(
        id=str(workspace.id),
        name=workspace.name,
        slug=workspace.slug,
        is_personal=workspace.is_personal,
    )


@router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Permanently delete the authenticated caller's account",
    description=(
        "Requires password confirmation. Refuses (409) when the caller "
        "solely owns a workspace that still has other members — ownership "
        "must be transferred or the workspace emptied first. Workspaces "
        "the caller owns alone (including their personal workspace) are "
        "deleted along with the account."
    ),
)
async def delete_account(
    body: DeleteAccountRequest,
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    response: Response,
) -> None:
    svc = AuthService(db, settings)
    try:
        await svc.delete_account(user=current_user, password=body.password)
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Password is incorrect",
        ) from exc
    except OwnerOfSharedWorkspaceError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"You are the sole owner of '{exc.organization_name}', which has "
                "other members. Transfer ownership or remove its other members "
                "before deleting your account."
            ),
        ) from exc
    clear_session_cookies(response, settings)


@router.post(
    "/onboarding/complete",
    response_model=UserPublic,
    summary="Mark the first-time onboarding wizard as completed",
    description=(
        "Called once, from the onboarding wizard's final step "
        "(apps/dashboard's /onboarding route). Idempotent — safe to call "
        "again, it just refreshes the completion timestamp."
    ),
)
async def complete_onboarding(
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
) -> UserPublic:
    svc = AuthService(db, settings)
    user = await svc.complete_onboarding(user=current_user)
    return _build_user_public(user)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke the current session",
)
async def logout(
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    request: Request,
    response: Response,
) -> None:
    clear_session_cookies(response, settings)

    auth_header = request.headers.get("authorization", "")
    raw_token: str | None
    if auth_header.lower().startswith("bearer "):
        raw_token = auth_header[7:].strip()
    else:
        raw_token = request.cookies.get(ACCESS_TOKEN_COOKIE)
    if not raw_token:
        return
    try:
        claims = decode_access_token(raw_token, settings=settings)
    except (ExpiredSignatureError, DecodeError, InvalidTokenError):
        return

    session_id_str = claims.get("jti")
    if not isinstance(session_id_str, str):
        return
    try:
        session_id = uuid.UUID(session_id_str)
    except ValueError:
        return

    svc = AuthService(db, settings)
    await svc.logout(session_id=session_id)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Rotate refresh token and issue a new access token",
)
async def refresh(
    body: RefreshRequest,
    response: Response,
    db: DbDep,
    settings: SettingsDep,
) -> TokenResponse:
    svc = AuthService(db, settings)
    try:
        pair = await svc.refresh(refresh_token=body.refresh_token)
    except AuthInvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is invalid or expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    set_session_cookies(response, pair, settings)
    return TokenResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        token_type="bearer",  # noqa: S106
        expires_in=pair.expires_in,
    )


async def _verify_email_and_respond(
    *, token: str, db: DbDep, settings: SettingsDep
) -> MessageResponse:
    """Shared body for the POST and GET verify-email variants below —
    exactly one place calls ``AuthService.verify_email`` and maps its
    exceptions to HTTP responses, so the two entry points can never drift."""
    svc = AuthService(db, settings)
    try:
        await svc.verify_email(token=token)
    except EmailAlreadyVerifiedError:
        # EP-24.4: never reveal token/verification-state details beyond
        # "already verified" — this specific case is safe to surface (it
        # tells the caller nothing a valid token holder doesn't already
        # know) and doubles as an idempotent success for a user who clicks
        # an old verification link a second time.
        return MessageResponse(message="Email address is already verified")
    except AuthInvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification token is invalid or expired",
        ) from exc
    return MessageResponse(message="Email verified successfully")


@router.post(
    "/verify-email",
    response_model=MessageResponse,
    summary="Verify an email address using a one-time token",
)
async def verify_email(
    body: VerifyEmailRequest,
    db: DbDep,
    settings: SettingsDep,
) -> MessageResponse:
    return await _verify_email_and_respond(token=body.token, db=db, settings=settings)


@router.get(
    "/verify-email",
    response_model=MessageResponse,
    summary="Verify an email address using a one-time token (link-click variant)",
    description=(
        "Same behavior as POST /verify-email, exposed as a GET so the "
        "verification link itself can be a plain, single-click URL. "
        "apps/dashboard's own /verify-email page still calls the POST "
        "variant from JavaScript (EP-05) — this GET endpoint is additive, "
        "not a replacement, kept for non-JS or direct-link integrations."
    ),
)
async def verify_email_get(
    db: DbDep,
    settings: SettingsDep,
    token: str = Query(min_length=1),
) -> MessageResponse:
    return await _verify_email_and_respond(token=token, db=db, settings=settings)


async def _request_verification_email(
    *, email: str, request: Request, db: DbDep, settings: SettingsDep
) -> MessageResponse:
    """Shared, rate-limited body for POST /resend-verification."""
    limiter = _get_email_rate_limiter(request)
    decision = await limiter.check_and_record(scope="verify", key=email.lower())
    if not decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many verification emails requested. Please try again later.",
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )
    svc = AuthService(db, settings)
    await svc.resend_verification_email(email=email)
    # Same response whether the account exists, is already verified, or
    # genuinely got a new email — never reveals which occurred (EP-24.4).
    return MessageResponse(
        message="If an account with that email exists and isn't verified, a new link has been sent"
    )


@router.post(
    "/resend-verification",
    response_model=MessageResponse,
    summary="Resend the email verification link",
)
async def resend_verification(
    body: ResendVerificationRequest,
    request: Request,
    db: DbDep,
    settings: SettingsDep,
) -> MessageResponse:
    return await _request_verification_email(
        email=body.email, request=request, db=db, settings=settings
    )


async def _request_password_reset_email(
    *, email: str, request: Request, db: DbDep, settings: SettingsDep
) -> MessageResponse:
    """Shared, rate-limited body for both the /forgot-password (EP-24.4) and
    the pre-existing /request-password-reset routes below — same handler,
    two mounted paths, so neither can silently drift from the other."""
    limiter = _get_email_rate_limiter(request)
    decision = await limiter.check_and_record(scope="reset", key=email.lower())
    if not decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many reset emails requested. Please try again later.",
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )
    svc = AuthService(db, settings)
    await svc.create_password_reset_token(email=email)
    return MessageResponse(
        message="If an account with that email exists, a reset link has been sent"
    )


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    summary="Request a password-reset email",
)
async def forgot_password(
    body: PasswordResetRequest,
    request: Request,
    db: DbDep,
    settings: SettingsDep,
) -> MessageResponse:
    return await _request_password_reset_email(
        email=body.email, request=request, db=db, settings=settings
    )


@router.post(
    "/request-password-reset",
    response_model=MessageResponse,
    summary="Request a password-reset email (alias of /forgot-password)",
    description=(
        "Pre-EP-24.4 name for this endpoint, kept mounted for backward "
        "compatibility (apps/dashboard's ForgotPassword.tsx already calls "
        "this path) — identical behavior to /forgot-password."
    ),
)
async def request_password_reset(
    body: PasswordResetRequest,
    request: Request,
    db: DbDep,
    settings: SettingsDep,
) -> MessageResponse:
    return await _request_password_reset_email(
        email=body.email, request=request, db=db, settings=settings
    )


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    summary="Reset password using a one-time token",
)
async def reset_password(
    body: ResetPasswordRequest,
    db: DbDep,
    settings: SettingsDep,
) -> MessageResponse:
    svc = AuthService(db, settings)
    try:
        await svc.reset_password(token=body.token, new_password=body.new_password)
    except AuthInvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token is invalid or expired",
        ) from exc
    return MessageResponse(message="Password has been reset successfully")


# ── Google OAuth (EP-24.5) ───────────────────────────────────────────────────


def _require_google_configured(settings: Settings) -> None:
    if not settings.google_oauth_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google sign-in is not configured on this deployment",
        )


def _google_redirect_uri(settings: Settings) -> str:
    """The backend's own callback URL — must exactly match a URI registered
    in Google Cloud Console. Distinct from `settings.dashboard_url`, which
    the callback redirects *to* once the session is established."""
    return f"{settings.api_base_url.rstrip('/')}/v1/auth/google/callback"


def _set_oauth_state_cookie(response: Response, token: str, settings: Settings) -> None:
    """Host-only (no `domain=`), short-lived cookie — see google_oauth.py's
    module docstring for why this is deliberately distinct from the
    cross-subdomain session cookies in app.auth.cookies."""
    response.set_cookie(
        google_oauth.OAUTH_STATE_COOKIE,
        token,
        max_age=google_oauth.STATE_TTL_MINUTES * 60,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        path="/",
    )


def _clear_oauth_state_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(google_oauth.OAUTH_STATE_COOKIE, path="/")


def _build_dashboard_handoff_url(
    *,
    path: str,
    pair: TokenPair,
    user: User,
    workspace: Organization | None,
    settings: Settings,
) -> str:
    """Python replica of apps/website/src/lib/api.ts's `buildDashboardHandoffUrl` —
    same base64-JSON-in-URL-fragment payload shape, so
    apps/dashboard/src/lib/consumeSessionHandoff.ts (unchanged) consumes a
    Google-login redirect exactly like a password-login redirect from the
    website. Fragments are never sent to any server (RFC 3986), so this
    carries no more exposure than the existing bearer-token-in-JS model."""
    payload: dict[str, Any] = {
        "access_token": pair.access_token,
        "refresh_token": pair.refresh_token,
        "user": {
            "id": user.external_id,
            "email": user.email,
            "username": user.username,
            "display_name": user.display_name,
            "status": user.status.value,
            "email_verified": user.email_verified,
            "onboarding_completed": user.onboarding_completed_at is not None,
            # EP-24.6.1 — Issue 1: lets ProtectedRoute force a first-time
            # Google user through /set-password before /onboarding, exactly
            # like onboarding_completed already gates the wizard itself.
            "password_configured": user.password_hash is not None,
        },
    }
    if workspace is not None:
        payload["workspace"] = {
            # EP-25.3: raw hyphenated UUID, not `workspace.external_id` —
            # this is what `consumeSessionHandoff.ts` feeds straight into
            # `useOrgStore.setOrganization()`, and every organization_id-
            # typed dashboard endpoint expects a plain UUID. Using
            # external_id here (as this line did before EP-25.3) silently
            # broke every Budget/Alert/Analytics/Dashboard/Usage/Pricing/
            # Projects/Connections request for a Google OAuth user, since
            # `AuthGuard` only renders `OrgSelector` (which would have
            # fetched and corrected it via GET /v1/organizations) when
            # `organizationId` is falsy — and the handoff always sets one.
            "id": str(workspace.id),
            "name": workspace.name,
            "is_personal": workspace.is_personal,
        }
    encoded = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
    fragment = quote(encoded, safe="")
    base = settings.dashboard_url.rstrip("/")
    return f"{base}{path}#session={fragment}"


@router.get(
    "/google/start",
    summary="Begin 'Continue with Google' login or registration",
    description=(
        "Public — no auth required. 302s to Google's OAuth consent screen. "
        "On success, GET /google/callback logs the user in (existing "
        "account, or one auto-linked by matching email) or registers a "
        "brand-new account + personal workspace with the email pre-verified."
    ),
)
async def google_start(settings: SettingsDep) -> RedirectResponse:
    _require_google_configured(settings)
    state_token, flow = google_oauth.encode_oauth_state(
        mode="login", redirect_path="/", settings=settings
    )
    challenge = google_oauth.pkce_challenge_from_verifier(flow.code_verifier)
    authorize_url = google_oauth.build_authorize_url(
        settings=settings,
        redirect_uri=_google_redirect_uri(settings),
        state=state_token,
        nonce=flow.nonce,
        code_challenge=challenge,
    )
    redirect = RedirectResponse(authorize_url, status_code=status.HTTP_302_FOUND)
    _set_oauth_state_cookie(redirect, state_token, settings)
    return redirect


@router.post(
    "/google/link",
    summary="Begin linking a Google account to the authenticated user",
    description=(
        "Returns the Google authorize URL to navigate to (Part 4). Requires "
        "an active session (Bearer token) — the returned OAuth state "
        "embeds this user's id, signed and tamper-proof, so the callback "
        "can complete the link without depending on a cross-domain cookie."
    ),
)
async def google_link_start(current_user: CurrentUser, settings: SettingsDep) -> JSONResponse:
    _require_google_configured(settings)
    state_token, flow = google_oauth.encode_oauth_state(
        mode="link",
        redirect_path="/settings",
        settings=settings,
        user_id=str(current_user.id),
    )
    challenge = google_oauth.pkce_challenge_from_verifier(flow.code_verifier)
    authorize_url = google_oauth.build_authorize_url(
        settings=settings,
        redirect_uri=_google_redirect_uri(settings),
        state=state_token,
        nonce=flow.nonce,
        code_challenge=challenge,
        login_hint=current_user.email,
    )
    response = JSONResponse({"authorize_url": authorize_url})
    _set_oauth_state_cookie(response, state_token, settings)
    return response


@router.get(
    "/google/callback",
    summary="Google OAuth callback — completes login, registration, or account linking",
    description=(
        "Google redirects the browser here after the consent screen. "
        "Never returns JSON — always a 302 back to the dashboard (on "
        "success) or the login page with a `google_error` query param (on "
        "any failure), since this is a top-level browser navigation, not "
        "an API call a frontend can await."
    ),
)
async def google_callback(
    request: Request,
    db: DbDep,
    settings: SettingsDep,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    dashboard_base = settings.dashboard_url.rstrip("/")
    ip = request.client.host if request.client else None

    def _fail(reason: str) -> RedirectResponse:
        log_auth_event(AuditEvent.OAUTH_FAILURE, ip_address=ip, reason=reason)
        redirect = RedirectResponse(
            f"{dashboard_base}/login?google_error={quote(reason)}",
            status_code=status.HTTP_302_FOUND,
        )
        _clear_oauth_state_cookie(redirect, settings)
        return redirect

    if error:
        return _fail("google_denied")
    if not settings.google_oauth_configured:
        return _fail("not_configured")
    if not code or not state:
        return _fail("missing_code_or_state")

    cookie_state = request.cookies.get(google_oauth.OAUTH_STATE_COOKIE)
    try:
        google_oauth.verify_state_match(cookie_value=cookie_state, query_value=state)
        flow = google_oauth.decode_oauth_state(state, settings=settings)
    except google_oauth.OAuthStateError:
        log_auth_event(AuditEvent.OAUTH_STATE_VALIDATION_FAILURE, ip_address=ip)
        return _fail("invalid_state")

    try:
        token_response = await google_oauth.exchange_code_for_tokens(
            settings=settings,
            code=code,
            redirect_uri=_google_redirect_uri(settings),
            code_verifier=flow.code_verifier,
        )
        identity = google_oauth.verify_google_id_token(
            id_token=token_response["id_token"],
            settings=settings,
            expected_nonce=flow.nonce,
        )
    except google_oauth.InvalidGoogleTokenError:
        log_auth_event(AuditEvent.OAUTH_INVALID_TOKEN, ip_address=ip)
        return _fail("invalid_token")
    except google_oauth.GoogleOAuthError:
        return _fail("token_exchange_failed")

    svc = AuthService(db, settings)
    ua = request.headers.get("user-agent")

    if flow.mode == "link":
        target_user_id = google_oauth.parse_user_id(flow.user_id)
        target_user = await svc.get_by_id(target_user_id) if target_user_id else None
        if target_user is None:
            return _fail("link_target_not_found")
        try:
            await svc.link_google(
                user=target_user,
                google_sub=identity.sub,
                google_email=identity.email,
                ip_address=ip,
            )
        except GoogleAccountAlreadyLinkedError:
            return _fail("already_linked")
        redirect = RedirectResponse(
            f"{dashboard_base}/settings?google_linked=1", status_code=status.HTTP_302_FOUND
        )
        _clear_oauth_state_cookie(redirect, settings)
        return redirect

    # mode == "login" — covers both an existing-user login and a brand-new registration.
    pair, user, org, is_new_user = await svc.login_or_register_with_google(
        google_sub=identity.sub,
        email=identity.email,
        display_name=identity.display_name,
        avatar_url=identity.avatar_url,
        ip_address=ip,
        user_agent=ua,
    )
    handoff_url = _build_dashboard_handoff_url(
        path="/onboarding" if is_new_user else "/",
        pair=pair,
        user=user,
        workspace=org,
        settings=settings,
    )
    redirect = RedirectResponse(handoff_url, status_code=status.HTTP_302_FOUND)
    set_session_cookies(redirect, pair, settings)
    _clear_oauth_state_cookie(redirect, settings)
    return redirect


@router.post(
    "/google/unlink",
    response_model=UserPublic,
    summary="Unlink Google from the authenticated user's account",
    description=(
        "Refuses (400) if the account has no password set — a Google-only "
        "account must always retain at least one way to sign in (Part 4)."
    ),
)
async def google_unlink(current_user: CurrentUser, db: DbDep, settings: SettingsDep) -> UserPublic:
    svc = AuthService(db, settings)
    try:
        user = await svc.unlink_google(user=current_user)
    except LastAuthMethodError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "This account has no password set — Google is the only way to "
                "sign in. Set a password before unlinking Google."
            ),
        ) from exc
    return _build_user_public(user)
