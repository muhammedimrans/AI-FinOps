"""Auth request/response schemas — EP-05 / F-017."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

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


class ResendVerificationRequest(BaseModel):
    """Email address to (re)send a verification link to (EP-24.4)."""

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Reset token plus the desired new password."""

    token: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=128)


class UpdateProfileRequest(BaseModel):
    """Partial profile update (EP-22.2 Settings — Profile section).

    Every field is optional; only the fields the caller actually supplied
    are applied (``exclude_unset`` in the endpoint) — omitting a field
    leaves it unchanged, it is never implicitly cleared. Email is
    intentionally not editable here (changing the account's login email is
    a distinct, higher-stakes flow not in this EP's scope).
    """

    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    username: str | None = Field(default=None, max_length=50)
    avatar_url: str | None = Field(default=None, max_length=2048)
    bio: str | None = Field(default=None, max_length=2000)
    timezone: str | None = Field(default=None, max_length=64)


class UpdatePreferencesRequest(BaseModel):
    """Shallow-merge patch applied to User.preferences (EP-22.2 Settings — Preferences section).

    Free-form: the frontend owns the key/value vocabulary (theme, timezone,
    currency, date_format, sidebar_collapsed, notifications, ...). Keys
    present here overwrite the corresponding stored key; keys not present
    are left untouched.
    """

    preferences: dict[str, Any] = Field(default_factory=dict)


class ChangePasswordRequest(BaseModel):
    """Current + new password for an authenticated in-session password change."""

    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=128)


class DeleteAccountRequest(BaseModel):
    """Password confirmation required to permanently delete the account."""

    password: str = Field(min_length=1)


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
    # EP-22.2 Settings — profile + account-metadata fields the Profile
    # section displays/edits, and the preferences bag the Preferences
    # section reads/writes.
    avatar_url: str | None
    bio: str | None
    timezone: str | None
    created_at: datetime
    preferences: dict[str, Any]
    # EP-24.5 Settings — "Linked accounts" display (Part 7). `google_email`
    # is only ever the address Google itself reported at link time (may
    # differ from `email` if the user's primary login email was set up
    # separately) — never a raw Google token or any other Google account
    # data.
    google_linked: bool
    google_email: str | None
    last_login_provider: str | None

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
