"""Auth-layer exceptions — EP-05."""

from __future__ import annotations


class AuthError(Exception):
    """Base class for authentication and authorization errors."""


class InvalidCredentialsError(AuthError):
    """Email/password pair is incorrect or the user does not exist."""


class AccountDisabledError(AuthError):
    """The user account has been disabled by an administrator."""


class InvalidTokenError(AuthError):
    """The provided token is invalid, expired, already used, or revoked."""


class EmailAlreadyVerifiedError(AuthError):
    """The user's email address has already been verified."""


# ── Organization API Key authentication (EP-15) ─────────────────────────────


class InvalidApiKeyError(AuthError):
    """The presented API key is missing, malformed, unknown, or revoked.

    Deliberately covers several distinct causes (no Authorization header, no
    Bearer scheme, empty token, unknown hash, soft-deleted key) with a single
    error type — the HTTP response must not let a caller distinguish "this
    key never existed" from "this key was revoked" from "you sent garbage".
    """


class ApiKeyExpiredError(AuthError):
    """The API key exists and is otherwise valid, but its expiry has passed."""


class OrganizationSuspendedError(AuthError):
    """The API key's owning organization is not ACTIVE (or no longer exists)."""


class InsufficientApiKeyPermissionsError(AuthError):
    """The API key is valid but was not granted the required permission scope."""
