"""Auth-layer exceptions — EP-05."""

from __future__ import annotations


class AuthError(Exception):
    """Base class for authentication and authorization errors."""


class InvalidCredentialsError(AuthError):
    """Email/password pair is incorrect or the user does not exist."""


class AccountDisabledError(AuthError):
    """The user account has been disabled by an administrator."""


class EmailNotVerifiedError(AuthError):
    """Password login was attempted before the account's email was verified.

    EP-24.4.1 — closes the login-time bypass: `register()` deliberately
    issues a session immediately for a brand-new (unverified) account (an
    existing, documented activation-funnel decision — see EP-21.2's note on
    `register()`), but a *separate* `login()` call with email+password must
    never succeed until that email is verified. Google OAuth logins are
    exempt (EP-24.5) — Google already verifies the address, so
    `login_or_register_with_google()` never raises this.
    """


class InvalidTokenError(AuthError):
    """The provided token is invalid, expired, already used, or revoked."""


class EmailAlreadyVerifiedError(AuthError):
    """The user's email address has already been verified."""


class EmailAlreadyRegisteredError(AuthError):
    """Registration was attempted with an email that already has an account."""


class UsernameAlreadyTakenError(AuthError):
    """Profile update was attempted with a username already used by another account."""


class OwnerOfSharedWorkspaceError(AuthError):
    """Account deletion was blocked because the user solely owns a workspace with other members.

    Carries the organization's name so the endpoint can return an
    actionable message (transfer ownership or remove the other members
    first) rather than a generic failure.
    """

    def __init__(self, organization_name: str) -> None:
        self.organization_name = organization_name
        super().__init__(organization_name)


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


# ── Google OAuth (EP-24.5) ───────────────────────────────────────────────────


class GoogleAccountAlreadyLinkedError(AuthError):
    """This Google account (by `sub`) is already linked to a different Costorah user."""


class LastAuthMethodError(AuthError):
    """Refused to unlink Google because it is the account's only login method.

    A user with no password set (a Google-only account) must always retain
    at least one way to authenticate — Part 4's "do not allow removing the
    final authentication method."
    """
