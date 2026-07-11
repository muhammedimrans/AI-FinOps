"""Resend delivery-event webhook receiver (EP-25.3).

Closes the "no delivery-event webhooks (bounce/complaint tracking)" gap
this codebase's own EP-24.4/EP-24.5/EP-24.6 "Future improvements" sections
have carried forward unresolved — see CLAUDE.md's EP-25.3 section for the
full architecture. This module owns exactly two things: verifying that an
inbound webhook request genuinely came from Resend (signature
verification), and turning a verified payload into a persisted
``EmailDeliveryEvent`` row + an audit log entry for failures. It never
sends email itself — ``EmailService``/``EmailProvider`` (EP-24.4) are
untouched by this EP.

## Signature scheme

Resend signs webhooks using Svix's standard scheme: three headers
(``svix-id``, ``svix-timestamp``, ``svix-signature``), where the signature
is ``base64(HMAC-SHA256(secret_bytes, f"{svix_id}.{svix_timestamp}.{body}"))``,
keyed by the base64-decoded portion of a ``whsec_<base64>``-formatted
secret. ``verify_signature()`` implements exactly this — a constant-time
comparison against every space-separated signature Svix may send (its
format allows multiple, versioned signatures in one header; this verifier
accepts a match against any of them, matching Svix's own documented
verification algorithm).
"""

from __future__ import annotations

import base64
import hmac
import time
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

import structlog

from app.auth.audit import AuditEvent, log_auth_event
from app.models.email_delivery_event import (
    FAILURE_EVENT_TYPES,
    EmailDeliveryEvent,
    EmailDeliveryEventType,
)
from app.repositories.email_delivery_event_repository import EmailDeliveryEventRepository

log = structlog.get_logger("email.webhook")

# Reject a webhook whose svix-timestamp is further than this from "now" —
# the standard Svix-recommended replay-protection window.
_TOLERANCE_SECONDS = 5 * 60


class WebhookVerificationError(Exception):
    """Raised when a webhook request fails signature verification."""


def verify_signature(
    *,
    payload: bytes,
    svix_id: str,
    svix_timestamp: str,
    svix_signature: str,
    secret: str,
) -> None:
    """Verify a Resend/Svix webhook signature. Raises
    ``WebhookVerificationError`` on any failure — timestamp too old/new,
    malformed secret, or no matching signature — never returns a boolean,
    so a caller can't accidentally ignore the result."""
    try:
        ts = int(svix_timestamp)
    except ValueError as exc:
        raise WebhookVerificationError("Malformed svix-timestamp header.") from exc

    if abs(time.time() - ts) > _TOLERANCE_SECONDS:
        raise WebhookVerificationError("Webhook timestamp outside the allowed tolerance window.")

    secret_prefix = "whsec_"  # noqa: S105 - a public format marker, not a secret value
    if not secret.startswith(secret_prefix):
        raise WebhookVerificationError("Malformed webhook secret (expected 'whsec_' prefix).")
    try:
        secret_bytes = base64.b64decode(secret[len(secret_prefix) :])
    except (ValueError, TypeError) as exc:
        raise WebhookVerificationError("Malformed webhook secret (invalid base64).") from exc

    signed_content = f"{svix_id}.{svix_timestamp}.".encode() + payload
    expected = base64.b64encode(hmac.new(secret_bytes, signed_content, sha256).digest()).decode()

    # svix-signature may contain multiple space-separated "v1,<sig>" entries
    # (e.g. during a secret rotation window) — a match against any is valid.
    candidates = [part.split(",", 1)[-1] for part in svix_signature.split()]
    if not any(hmac.compare_digest(expected, candidate) for candidate in candidates):
        raise WebhookVerificationError("Signature does not match any provided candidate.")


@dataclass(frozen=True, slots=True)
class ProcessedWebhookEvent:
    """Outcome of processing one verified webhook payload."""

    event_type: str
    provider_message_id: str
    recipient_email: str
    is_failure: bool


async def process_resend_webhook_payload(
    payload: dict[str, Any],
    *,
    repo: EmailDeliveryEventRepository,
) -> ProcessedWebhookEvent | None:
    """Persist one verified Resend webhook payload as an ``EmailDeliveryEvent``.

    Returns ``None`` (and persists nothing) for a payload shape this
    receiver doesn't recognize — an unknown event ``type`` or a missing
    ``data.email_id`` — rather than raising, since Resend's own webhook
    delivery retries on a non-2xx response; an unrecognized-but-harmless
    payload should not trigger Resend's retry storm.
    """
    event_type_raw = payload.get("type")
    data = payload.get("data") or {}
    provider_message_id = data.get("email_id")

    if not event_type_raw or not provider_message_id:
        log.warning("resend_webhook_missing_fields", payload_keys=list(payload.keys()))
        return None

    try:
        event_type = EmailDeliveryEventType(event_type_raw)
    except ValueError:
        log.info("resend_webhook_unrecognized_event_type", event_type=event_type_raw)
        return None

    recipient = data.get("to")
    # Resend's `to` is a list; this codebase only ever sends to one
    # recipient per message (EmailMessage.to is a single string), so the
    # first entry is always the one that matters.
    recipient_email = (
        recipient[0] if isinstance(recipient, list) and recipient else str(recipient or "")
    )
    subject = data.get("subject")
    tags_raw = data.get("tags") or {}
    tags = {str(k): str(v) for k, v in tags_raw.items()} if isinstance(tags_raw, dict) else {}

    event = EmailDeliveryEvent(
        provider_message_id=provider_message_id,
        event_type=event_type.value,
        recipient_email=recipient_email,
        subject=subject,
        tags=tags,
        raw_payload=data,
    )
    await repo.create(event)

    is_failure = event_type in FAILURE_EVENT_TYPES
    if is_failure:
        log_auth_event(
            AuditEvent.EMAIL_DELIVERY_FAILURE,
            email=recipient_email,
            reason=event_type.value,
            provider_message_id=provider_message_id,
        )
        log.warning(
            "resend_delivery_failure",
            event_type=event_type.value,
            provider_message_id=provider_message_id,
        )
    else:
        log.info(
            "resend_delivery_event",
            event_type=event_type.value,
            provider_message_id=provider_message_id,
        )

    return ProcessedWebhookEvent(
        event_type=event_type.value,
        provider_message_id=provider_message_id,
        recipient_email=recipient_email,
        is_failure=is_failure,
    )
