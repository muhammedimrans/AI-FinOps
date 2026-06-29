"""
Domain-level validation utilities.

These validators enforce invariants that cannot be expressed as PostgreSQL
constraints. They are called by the service layer before persisting data to
the database.

Design rules:
  - Validators raise ValueError with a human-readable message on violation.
  - Validators never mutate their input.
  - Validators are pure functions: no database I/O, no side effects.
"""

from __future__ import annotations

import re
import zoneinfo
from typing import Any

# -- User ---------------------------------------------------------------------

_EMAIL_RE: re.Pattern[str] = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
_USERNAME_RE: re.Pattern[str] = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9_-]*[a-zA-Z0-9])?$")
_LOCALE_RE: re.Pattern[str] = re.compile(r"^[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")

_EMAIL_MAX = 320
_DISPLAY_NAME_MIN = 1
_DISPLAY_NAME_MAX = 255
_USERNAME_MIN = 3
_USERNAME_MAX = 50
_LOCALE_MAX = 35
_TIMEZONE_MAX = 64

# Cache at import time - available_timezones() performs file I/O.
_VALID_TIMEZONES: frozenset[str] = frozenset(zoneinfo.available_timezones())


def validate_user_email(email: str) -> None:
    """
    Reject obviously invalid email addresses.

    Uses a conservative RFC 5321-compatible regex. Full RFC 5322 parsing is
    deferred to the email-validator library in the API layer. This validator
    is the fast in-process guard before any DB round-trip.

    Args:
        email: The email address string to validate.

    Raises:
        ValueError: If the address is empty, too long, or does not match the
                    expected ``local@domain.tld`` pattern.
    """
    if not email or not email.strip():
        raise ValueError("User email must not be empty.")
    if len(email) > _EMAIL_MAX:
        raise ValueError(
            f"User email must not exceed {_EMAIL_MAX} characters " f"(got {len(email)})."
        )
    if not _EMAIL_RE.match(email.strip()):
        raise ValueError(f"User email {email!r} is not a valid email address.")


def validate_display_name(display_name: str) -> None:
    """
    Reject empty or excessively long display names.

    Args:
        display_name: The name string to validate.

    Raises:
        ValueError: If the name is blank or exceeds 255 characters.
    """
    stripped = display_name.strip() if display_name else ""
    if len(stripped) < _DISPLAY_NAME_MIN:
        raise ValueError("User display_name must not be empty.")
    if len(display_name) > _DISPLAY_NAME_MAX:
        raise ValueError(
            f"User display_name must not exceed {_DISPLAY_NAME_MAX} characters "
            f"(got {len(display_name)})."
        )


def validate_username(username: str) -> None:
    """
    Enforce username format rules.

    Rules:
      - 3 to 50 characters.
      - Only alphanumeric characters, underscores, and hyphens.
      - Must start and end with an alphanumeric character.

    Args:
        username: The username string to validate.

    Raises:
        ValueError: If the username violates any rule.
    """
    if not username or not username.strip():
        raise ValueError("User username must not be empty.")
    stripped = username.strip()
    if len(stripped) < _USERNAME_MIN:
        raise ValueError(
            f"User username must be at least {_USERNAME_MIN} characters " f"(got {len(stripped)})."
        )
    if len(stripped) > _USERNAME_MAX:
        raise ValueError(
            f"User username must not exceed {_USERNAME_MAX} characters " f"(got {len(stripped)})."
        )
    if not _USERNAME_RE.match(stripped):
        raise ValueError(
            f"User username {username!r} is invalid. "
            "Usernames may contain letters, digits, underscores, and hyphens, "
            "and must start and end with a letter or digit."
        )


def validate_locale(locale: str) -> None:
    """
    Validate a BCP 47 locale tag (e.g. ``en``, ``en-US``, ``zh-Hans-CN``).

    Accepts 2-3 letter language code optionally followed by subtags separated
    by hyphens (2-8 alphanumeric characters each).

    Args:
        locale: The locale string to validate.

    Raises:
        ValueError: If the locale string is empty, too long, or malformed.
    """
    if not locale or not locale.strip():
        raise ValueError("User locale must not be empty.")
    stripped = locale.strip()
    if len(stripped) > _LOCALE_MAX:
        raise ValueError(
            f"User locale must not exceed {_LOCALE_MAX} characters " f"(got {len(stripped)})."
        )
    if not _LOCALE_RE.match(stripped):
        raise ValueError(
            f"User locale {locale!r} is not a valid BCP 47 locale tag. "
            "Expected format: 'en', 'en-US', 'zh-Hans-CN', etc."
        )


def validate_timezone(timezone: str) -> None:
    """
    Validate an IANA timezone identifier (e.g. ``UTC``, ``America/New_York``).

    Uses the ``zoneinfo`` standard library set cached at import time.

    Args:
        timezone: The timezone string to validate.

    Raises:
        ValueError: If the timezone string is empty or not a known IANA key.
    """
    if not timezone or not timezone.strip():
        raise ValueError("User timezone must not be empty.")
    stripped = timezone.strip()
    if len(stripped) > _TIMEZONE_MAX:
        raise ValueError(
            f"User timezone must not exceed {_TIMEZONE_MAX} characters " f"(got {len(stripped)})."
        )
    if stripped not in _VALID_TIMEZONES:
        raise ValueError(f"User timezone {timezone!r} is not a valid IANA timezone identifier.")


# -- Provider Configuration ---------------------------------------------------

# Exact key names that are prohibited in ProviderConnection.configuration.
_PROHIBITED_CONFIG_KEYS: frozenset[str] = frozenset(
    {
        "api_key",
        "apikey",
        "secret",
        "secret_key",
        "secretkey",
        "password",
        "passwd",
        "access_token",
        "accesstoken",
        "refresh_token",
        "refreshtoken",
        "bearer_token",
        "bearertoken",
        "auth_token",
        "authtoken",
        "token",
        "client_secret",
        "clientsecret",
        "private_key",
        "privatekey",
        "credential",
        "credentials",
        "authorization",
    }
)


def validate_provider_configuration(configuration: dict[str, Any]) -> None:
    """
    Reject any configuration dict containing secret-pattern keys.

    The ProviderConnection.configuration JSONB column stores non-sensitive
    provider metadata only (e.g., base URLs, timeout settings, model aliases).
    API keys, tokens, and credentials belong in the Secrets store, referenced
    by an opaque ID - never stored in this column.

    Args:
        configuration: The dict to validate (shallow key check, case-insensitive).

    Raises:
        ValueError: If any key matches a prohibited credential pattern, listing
                    all violations so the caller can return them together.

    Example::

        validate_provider_configuration({"base_url": "https://api.openai.com/v1"})  # OK
        validate_provider_configuration({"api_key": "sk-..."})  # raises ValueError
    """
    if not configuration:
        return

    violations: list[str] = []
    for key in configuration:
        normalised = key.lower().replace("-", "_").replace(" ", "_")
        if normalised in _PROHIBITED_CONFIG_KEYS:
            violations.append(repr(key))

    if violations:
        keys_str = ", ".join(sorted(violations))
        raise ValueError(
            f"ProviderConnection.configuration must not contain credential fields. "
            f"Prohibited key(s) found: {keys_str}. "
            f"Store secrets in the Secrets store and reference them by ID."
        )
