"""Authentication API — EP-05 / F-017.

Endpoints:
  POST /v1/auth/login                — issue access + refresh tokens
  POST /v1/auth/logout               — revoke the current session
  POST /v1/auth/refresh              — rotate refresh token, issue new access token
  POST /v1/auth/verify-email         — consume an email verification token
  POST /v1/auth/request-password-reset — request a password-reset link
  POST /v1/auth/reset-password       — consume a reset token and set a new password
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from jwt.exceptions import DecodeError, ExpiredSignatureError, InvalidTokenError

from app.api.deps import DbDep, SettingsDep
from app.auth.dependencies import CurrentUser
from app.auth.exceptions import (
    AccountDisabledError,
    EmailAlreadyVerifiedError,
    InvalidCredentialsError,
)
from app.auth.exceptions import InvalidTokenError as AuthInvalidTokenError
from app.auth.service import AuthService
from app.auth.tokens import decode_access_token
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    MessageResponse,
    PasswordResetRequest,
    RefreshRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserPublic,
    VerifyEmailRequest,
)

router = APIRouter(prefix="/auth", tags=["authentication"])


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
    "/login",
    response_model=LoginResponse,
    summary="Authenticate with email and password",
)
async def login(
    body: LoginRequest,
    request: Request,
    db: DbDep,
    settings: SettingsDep,
) -> LoginResponse:
    svc = AuthService(db, settings)
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    try:
        pair, user = await svc.login(
            email=body.email,
            password=body.password,
            ip_address=ip,
            user_agent=ua,
        )
    except InvalidCredentialsError as exc:
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
    return LoginResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        token_type="bearer",  # noqa: S106
        expires_in=pair.expires_in,
        user=_build_user_public(user),
    )


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
) -> None:
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        return
    raw_token = auth_header[7:].strip()
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
