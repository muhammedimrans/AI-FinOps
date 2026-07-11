"""Inbound webhook receivers — EP-25.3.

Public by nature (no ``CurrentUser``/``RequirePermission`` — the caller is
Resend's own infrastructure, not a logged-in user), secured instead by
Svix/HMAC signature verification (``app/email/webhook.py``). This mirrors
how every other "the caller isn't a Costorah user" endpoint in this
codebase (e.g. the Google OAuth callback, ``app/api/v1/auth.py``) is
public-but-verified rather than authenticated in the RBAC sense.
"""

from __future__ import annotations

import json

import structlog
from fastapi import APIRouter, Header, HTTPException, Request, status

from app.api.deps import DbDep, SettingsDep
from app.email.webhook import (
    WebhookVerificationError,
    process_resend_webhook_payload,
    verify_signature,
)
from app.repositories.email_delivery_event_repository import EmailDeliveryEventRepository

log = structlog.get_logger("email.webhook")

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post(
    "/resend",
    status_code=status.HTTP_200_OK,
    summary="Resend delivery-event webhook receiver",
    description=(
        "EP-25.3: receives Delivered/Bounced/Complained/Delayed/Sent/Opened/"
        "Clicked callbacks from Resend, verifies the Svix/HMAC signature, "
        "and persists each as an EmailDeliveryEvent. Returns 503 if "
        "RESEND_WEBHOOK_SECRET isn't configured, 401 on a bad signature — "
        "both intentionally non-2xx so Resend's own retry logic (which "
        "backs off and retries non-2xx responses) has a chance to redeliver "
        "once configuration/transient issues are fixed."
    ),
)
async def resend_webhook(
    request: Request,
    db: DbDep,
    settings: SettingsDep,
    svix_id: str | None = Header(default=None, alias="svix-id"),
    svix_timestamp: str | None = Header(default=None, alias="svix-timestamp"),
    svix_signature: str | None = Header(default=None, alias="svix-signature"),
) -> dict[str, bool]:
    if not settings.resend_webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Delivery-event webhooks are not configured on this deployment.",
        )
    if not (svix_id and svix_timestamp and svix_signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing required Svix signature headers.",
        )

    body = await request.body()
    try:
        verify_signature(
            payload=body,
            svix_id=svix_id,
            svix_timestamp=svix_timestamp,
            svix_signature=svix_signature,
            secret=settings.resend_webhook_secret.get_secret_value(),
        )
    except WebhookVerificationError as exc:
        log.warning("resend_webhook_signature_rejected", reason=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Webhook signature verification failed.",
        ) from exc

    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed webhook payload.",
        ) from exc

    repo = EmailDeliveryEventRepository(db)
    result = await process_resend_webhook_payload(parsed, repo=repo)
    return {"processed": result is not None}
