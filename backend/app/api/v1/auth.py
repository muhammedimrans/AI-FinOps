"""Authentication API — EP-05 / F-017, extended by EP-21.2.

Endpoints:
  POST /v1/auth/register             — create a User + personal workspace, issue a session
  POST /v1/auth/login                — issue access + refresh tokens
  POST /v1/auth/logout               — revoke the current session
  POST /v1/auth/refresh              — rotate refresh token, issue new access token
  GET  /v1/auth/me                   — the authenticated caller's profile
  POST /v1/auth/verify-email         — consume an email verification token
  POST /v1/auth/request-password-reset — request a password-reset link
  POST /v1/auth/reset-password       — consume a reset token and set a new password

Session cookies (EP-21.2): login, register, and refresh additionally set
httpOnly `costorah_access_token`/`costorah_refresh_token` cookies
(app.auth.cookies) alongside the unchanged JSON token response — existing
bearer-token clients (apps/dashboard) are unaffected; apps/website relies
on the cookie. logout clears both cookies.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status
from jwt.exceptions import DecodeError, ExpiredSignatureError, InvalidTokenError

from app.api.deps import DbDep, SettingsDep
from app.auth.cookies import ACCESS_TOKEN_COOKIE, clear_session_cookies, set_session_cookies
from app.auth.dependencies import CurrentUser
from app.auth.exceptions import (
    AccountDisabledError,
    EmailAlreadyRegisteredError,
    EmailAlreadyVerifiedError,
    InvalidCredentialsError,
)
from app.auth.exceptions import InvalidTokenError as AuthInvalidTokenError
from app.auth.rate_limit import LoginRateLimiter
from app.auth.service import AuthService
from app.auth.tokens import decode_access_token
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    MessageResponse,
    PasswordResetRequest,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    ResetPasswordRequest,
    TokenResponse,
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


def _build_user_public(user: Any) -> UserPublic:  # noqa: ANN401
    return UserPublic(
        id=user.external_id,
        email=user.email,
        username=user.username,
        display_name=user.display_name,
        status=user.status,
        email_verified=user.email_verified,
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
    svc = AuthService(db, settings)
    try:
        await svc.verify_email(token=body.token)
    except EmailAlreadyVerifiedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email address is already verified",
        ) from exc
    except AuthInvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification token is invalid or expired",
        ) from exc
    return MessageResponse(message="Email verified successfully")


@router.post(
    "/request-password-reset",
    response_model=MessageResponse,
    summary="Request a password-reset email",
)
async def request_password_reset(
    body: PasswordResetRequest,
    db: DbDep,
    settings: SettingsDep,
) -> MessageResponse:
    svc = AuthService(db, settings)
    await svc.create_password_reset_token(email=body.email)
    return MessageResponse(
        message="If an account with that email exists, a reset link has been sent"
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
