"""EmailDeliveryEvent ORM model — Resend delivery-event webhook log (EP-25.3).

Closes the "no delivery-event webhooks (bounce/complaint tracking)" gap
every EP since EP-24.4 has carried forward in its "Future improvements"
list (§24, §25, §27). Nothing about *sending* email changes — this is a
pure, additive receiver: Resend calls back into this table whenever a
previously-sent message's delivery status changes.

No "sent emails" table existed before this EP (sends were fire-and-forget,
per every prior EP's own EmailService design), so this table is
deliberately both the delivery-event log *and* the first persisted record
of email outcomes at all — reusing a single table for both rather than
adding a parallel "sent emails" entity purely to correlate against, which
would be exactly the kind of speculative table this codebase's "avoid
unnecessary tables" convention (EP-22.2, EP-23.4, EP-24.2) argues against.
Correlation back to *why* an email was sent (registration, invitation,
password reset, ...) is via ``EmailMessage.tags`` (already threaded through
every ``EmailService.send_*`` call) mirrored onto this row's ``tags``
column, not a foreign key to a specific auth/invitation row — Resend's
webhook payload has no such foreign key to give us either.
"""

from __future__ import annotations

import enum

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.mixins import BaseModel


class EmailDeliveryEventType(enum.StrEnum):
    """The Resend webhook event types this receiver understands.

    Mirrors Resend's own ``type`` field values exactly (``email.<x>``) so
    the mapping from webhook payload to stored event is a direct, lossless
    pass-through — never a lossy re-interpretation.
    """

    SENT = "email.sent"
    DELIVERED = "email.delivered"
    DELIVERY_DELAYED = "email.delivery_delayed"
    BOUNCED = "email.bounced"
    COMPLAINED = "email.complained"
    OPENED = "email.opened"
    CLICKED = "email.clicked"


# Event types this codebase treats as failures worth auditing loudly
# (app/email/webhook.py logs an EMAIL_DELIVERY_FAILURE audit event for
# exactly these — see that module for why SENT/DELIVERED/OPENED/CLICKED
# don't warrant the same treatment).
FAILURE_EVENT_TYPES = frozenset(
    {
        EmailDeliveryEventType.BOUNCED,
        EmailDeliveryEventType.COMPLAINED,
        EmailDeliveryEventType.DELIVERY_DELAYED,
    }
)


class EmailDeliveryEvent(BaseModel):
    """One Resend webhook delivery-status callback, stored verbatim.

    Append-only — a given ``provider_message_id`` can have many rows over
    its lifetime (sent -> delivered -> opened -> clicked, or
    sent -> bounced), each a distinct event, not an update to a prior row.
    ``get_latest_status_for_message`` (repository) derives "current
    delivery status" from this log by taking the most recent row, the same
    "status is derived from an event log, never itself a separately
    maintained field" pattern ``UsageCollectionRun``/``Alert`` already use.
    """

    __tablename__ = "email_delivery_events"

    provider_message_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    recipient_email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # EmailMessage.tags, mirrored — e.g. {"purpose": "verification"} —
    # the correlation mechanism described in this module's docstring above.
    tags: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    # The raw Resend webhook payload's `data` object, stored verbatim for
    # audit/debugging — never includes credential material (Resend's own
    # payload shape has none), only message metadata (recipient, subject,
    # timestamps, bounce/complaint reason codes).
    raw_payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
