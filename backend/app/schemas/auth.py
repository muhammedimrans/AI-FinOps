"""Auth request/response schemas — EP-05 / F-017."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, EmailStr, Field

# ── Request schemas ───────────────────────────────────────────────────────────


class LoginRequest(BaseModel):
    """Credentials for password-based login."""

    email: EmailStr
    password: str = Field(min_length=1)


class RegisterRequest(BaseModel):
    """New-account details for self-serve registration (EP-21.2)."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=255)


class RefreshRequest(BaseModel):
    """Opaque refresh token for access-token rotation."""

    refresh_token: str = Field(min_length=1)


class VerifyEmailRequest(BaseModel):
    """Raw email verification token sent to the user's inbox."""

    token: str = Field(min_length=1)


class PasswordResetRequest(BaseModel):
    """Email address to send a password-reset link to."""

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Reset token plus the desired new password."""

    token: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=128)


# ── Response schemas ──────────────────────────────────────────────────────────


class UserPublic(BaseModel):
    """Publicly-safe representation of a user in auth responses."""

    id: str
    email: str
    username: str | None
    display_name: str
    status: str
    email_verified: bool
    # EP-21.3: True once the first-time onboarding wizard (apps/dashboard's
    # /onboarding route) has been completed. Derived from
    # User.onboarding_completed_at (NULL = not yet) — see that column's
    # docstring for the backfill behavior on pre-existing users.
    onboarding_completed: bool

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    """JWT access token plus opaque refresh token."""

    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105
    expires_in: int


class LoginResponse(TokenResponse):
    """Token pair plus the authenticated user's profile."""

    user: UserPublic


class WorkspacePublic(BaseModel):
    """Publicly-safe representation of an Organization used as a workspace."""

    id: str
    name: str
    slug: str
    is_personal: bool

    model_config = {"from_attributes": True}


class RegisterResponse(TokenResponse):
    """Token pair, the new user's profile, and their auto-created personal workspace."""

    user: UserPublic
    workspace: WorkspacePublic


class MessageResponse(BaseModel):
    """Generic confirmation message."""

    message: str
