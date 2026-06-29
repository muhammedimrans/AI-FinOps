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
