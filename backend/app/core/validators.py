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
from typing import Any

# ── User ──────────────────────────────────────────────────────────────────────

_EMAIL_RE: re.Pattern[str] = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")

_DISPLAY_NAME_MIN = 1
_DISPLAY_NAME_MAX = 255
_EMAIL_MAX = 320


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


# ── Provider Configuration ────────────────────────────────────────────────────

# Exact key names that are prohibited in ProviderConnection.configuration.
# These are well-known credential field names; storing them in configuration
# (a non-encrypted JSONB column) would expose secrets in plaintext.
#
# The actual credentials must be stored in the Secrets store and referenced
# by an opaque ID (per §4.5 / §4.15). This validator is the enforcement gate.
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
    by an opaque ID — never stored in this column.

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
