"""Organization/membership audit logging — EP-24.6.

Structured-log-based, not a new database table — the exact same
"structlog is the durable audit sink" convention ``app/auth/audit.py``
already established (EP-24.4) for authentication events, applied here to
organization-membership lifecycle events instead (invitations, role
changes, removals, ownership transfers). A separate module/log stream
(``org.audit`` vs. ``auth.audit``) rather than extending
``app.auth.audit.AuditEvent`` directly — invitations and membership
changes are an organization-management concern, not an authentication
one, even though the *mechanism* (one closed enum, one logging function,
no secrets ever passable through it) is identical by design.
"""

from __future__ import annotations

import enum
import uuid

import structlog

log = structlog.get_logger("org.audit")


class OrgAuditEvent(enum.StrEnum):
    """The fixed vocabulary of auditable organization/membership events (EP-24.6)."""

    INVITATION_SENT = "invitation_sent"
    INVITATION_RESENT = "invitation_resent"
    INVITATION_ACCEPTED = "invitation_accepted"
    INVITATION_DECLINED = "invitation_declined"
    INVITATION_CANCELLED = "invitation_cancelled"
    INVITATION_EXPIRED_ACCEPT_ATTEMPT = "invitation_expired_accept_attempt"
    INVITATION_INVALID_TOKEN = "invitation_invalid_token"  # noqa: S105
    MEMBER_ROLE_CHANGED = "member_role_changed"
    MEMBER_REMOVED = "member_removed"
    OWNERSHIP_TRANSFERRED = "ownership_transferred"


def log_org_event(
    event: OrgAuditEvent,
    *,
    organization_id: uuid.UUID | str | None = None,
    actor_user_id: uuid.UUID | str | None = None,
    target_email: str | None = None,
    **extra: str | int | bool | None,
) -> None:
    """Emit one structured audit-log line for an organization/membership event.

    ``organization_id`` is optional — an invalid/unrecognized invitation
    token (EP-24.6 Part 16's "do not leak information about invitations")
    means the org is genuinely unknown at the point of failure, so this is
    logged as ``None`` rather than a fabricated placeholder id.

    Mirrors ``app.auth.audit.log_auth_event``'s field discipline exactly:
    no parameter through which a secret (raw invitation token) could ever
    be passed, so no call site can accidentally leak one into a log line.
    """
    log.info(
        "org_audit",
        audit_event=event.value,
        organization_id=str(organization_id) if organization_id is not None else None,
        actor_user_id=str(actor_user_id) if actor_user_id is not None else None,
        target_email=target_email,
        **extra,
    )
