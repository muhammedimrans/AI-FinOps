"""Authentication API — EP-05 / F-017, extended by EP-21.2, EP-24.4.

Endpoints:
  POST /v1/auth/register             — create a User + personal workspace, issue a session
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

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from jwt.exceptions import DecodeError, ExpiredSignatureError, InvalidTokenError

from app.api.deps import DbDep, SettingsDep
from app.auth.cookies import ACCESS_TOKEN_COOKIE, clear_session_cookies, set_session_cookies
from app.auth.dependencies import CurrentUser
from app.auth.exceptions import (
    AccountDisabledError,
    EmailAlreadyRegisteredError,
    EmailAlreadyVerifiedError,
    InvalidCredentialsError,
    OwnerOfSharedWorkspaceError,
    UsernameAlreadyTakenError,
)
from app.auth.exceptions import InvalidTokenError as AuthInvalidTokenError
from app.auth.rate_limit import EmailRateLimiter, LoginRateLimiter
from app.auth.service import AuthService
from app.auth.tokens import decode_access_token
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
    TokenResponse,
    UpdatePreferencesRequest,
    UpdateProfileRequest,
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
    )


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account, personal workspace, and session",
)
async def register(
    body: RegisterRequest,
    request: Request,
    response: Response,
    db: DbDep,
    settings: SettingsDep,
) -> RegisterResponse:
    svc = AuthService(db, settings)
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    try:
        pair, user, workspace = await svc.register(
            email=body.email,
            password=body.password,
            display_name=body.display_name,
            ip_address=ip,
            user_agent=ua,
        )
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        ) from exc

    set_session_cookies(response, pair, settings)
    return RegisterResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        token_type="bearer",  # noqa: S106
        expires_in=pair.expires_in,
        user=_build_user_public(user),
        workspace=WorkspacePublic(
            id=workspace.external_id,
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
