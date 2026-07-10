"""Authentication audit logging — EP-24.4.

Structured-log-based, not a new database table. This codebase already
treats structlog as the durable record for every other significant
lifecycle event with no dedicated audit table of its own (scheduler job
history — CLAUDE.md §20; budget-alert firing — §22; provider sync runs —
§19) — those all rely on structured, greppable/queryable log output (this
platform's log aggregation is the actual audit sink) rather than a
second, parallel persistence layer purpose-built for "did X happen."
Authentication events follow the same convention here rather than
introducing a bespoke ``auth_audit_log`` table whose only consumer would
be the same log pipeline these events already flow into.

Every event is logged through this one function so the field vocabulary
(``event``, ``user_id``, ``email``, ``ip_address``) stays consistent and
callers can never accidentally interpolate a secret (raw token, password,
API key) into a log line — ``AuditEvent`` is a closed enum of event names,
and this module's own type signature has no parameter through which a
secret could be passed.
"""

from __future__ import annotations

import enum
import uuid

import structlog

log = structlog.get_logger("auth.audit")


class AuditEvent(enum.StrEnum):
    """The fixed vocabulary of auditable authentication events (EP-24.4 Part 8)."""

    REGISTRATION = "registration"
    VERIFICATION_EMAIL_SENT = "verification_email_sent"
    VERIFICATION_SUCCESS = "verification_success"
    VERIFICATION_FAILURE = "verification_failure"
    PASSWORD_RESET_REQUESTED = "password_reset_requested"  # noqa: S105
    PASSWORD_RESET_COMPLETED = "password_reset_completed"  # noqa: S105
    PASSWORD_CHANGED = "password_changed"  # noqa: S105
    ACCOUNT_LOCKED = "account_locked"  # future-ready — not fired by this EP

    # ── Google OAuth (EP-24.5, Part 10) ─────────────────────────────────────
    GOOGLE_LOGIN = "google_login"
    GOOGLE_REGISTRATION = "google_registration"
    GOOGLE_ACCOUNT_LINKED = "google_account_linked"
    GOOGLE_ACCOUNT_UNLINKED = "google_account_unlinked"
    OAUTH_FAILURE = "oauth_failure"
    OAUTH_INVALID_TOKEN = "oauth_invalid_token"  # noqa: S105
    OAUTH_STATE_VALIDATION_FAILURE = "oauth_state_validation_failure"


def log_auth_event(
    event: AuditEvent,
    *,
    user_id: uuid.UUID | str | None = None,
    email: str | None = None,
    ip_address: str | None = None,
    **extra: str | int | bool | None,
) -> None:
    """Emit one structured audit-log line for an authentication event.

    ``email`` is logged as-is (not hashed) — it is already the durable
    identifier every other log line in this codebase uses for a user
    (``AuthService``'s own existing ``log.warning(..., email=email)``
    call sites), and it is not a secret. Never pass a raw token, password,
    or API key via ``extra`` — this function has no parameter for one, by
    design (see module docstring).
    """
    log.info(
        "auth_audit",
        audit_event=event.value,
        user_id=str(user_id) if user_id is not None else None,
        email=email,
        ip_address=ip_address,
        **extra,
    )
