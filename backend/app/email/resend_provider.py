"""ResendEmailProvider — EmailProvider implementation for Resend (EP-24.4).

Reuses ``app.http.transport.HttpxTransport`` (EP-06/EP-07's generic,
provider-agnostic HTTP transport — already supports injecting an
``httpx.MockTransport`` for tests) rather than standing up a second HTTP
client abstraction. Does not reuse ``app.http.client.ProviderHttpClient``:
that layer's retry policy is keyed to the AI-provider error taxonomy
(``app.providers.errors``), which has no meaningful mapping onto an email
API's failure modes — reusing it here would mean bending an unrelated
abstraction to fit, not genuine reuse.
"""

from __future__ import annotations

import httpx
import structlog

from app.email.provider import EmailMessage, EmailProvider, EmailSendResult
from app.http.transport import HttpTransport, HttpxTransport

log = structlog.get_logger(__name__)

_RESEND_BASE_URL = "https://api.resend.com"


class ResendEmailProvider(EmailProvider):
    """Sends email via Resend's REST API (``POST /emails``).

    Never hardcodes credentials: ``api_key``/``from_email`` are read from
    ``Settings.resend_api_key``/``Settings.email_from`` at construction time
    by ``EmailService``, exactly as every other credentialed integration in
    this codebase reads its secret from ``Settings`` rather than the
    environment directly.
    """

    def __init__(
        self,
        *,
        api_key: str | None,
        from_email: str | None,
        transport: HttpTransport | None = None,
        mock_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._from_email = from_email
        self._transport = transport or HttpxTransport(
            base_url=_RESEND_BASE_URL,
            mock_transport=mock_transport,
        )

    @property
    def is_configured(self) -> bool:
        """True once both a key and a from-address are present."""
        return bool(self._api_key) and bool(self._from_email)

    async def send_email(self, message: EmailMessage) -> EmailSendResult:
        if not self.is_configured:
            # Never a hard failure: registration/reset/verification flows
            # must keep working even when email delivery isn't configured
            # (local dev, CI, a not-yet-provisioned environment) — see
            # EmailSendResult.skipped's own docstring.
            log.warning(
                "email_send_skipped_unconfigured",
                to_domain=message.to.rsplit("@", 1)[-1] if "@" in message.to else None,
                subject=message.subject,
            )
            return EmailSendResult(success=False, skipped=True)

        payload: dict[str, object] = {
            "from": self._from_email,
            "to": [message.to],
            "subject": message.subject,
            "html": message.html_body,
            "text": message.text_body,
        }
        if message.reply_to:
            payload["reply_to"] = message.reply_to
        if message.tags:
            payload["tags"] = [{"name": k, "value": v} for k, v in message.tags.items()]

        try:
            response = await self._transport.request(
                "POST",
                "/emails",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=15.0,
            )
        except httpx.HTTPError as exc:
            # Never log message.to/subject content beyond what's already
            # logged above, and never the API key — str(exc) for an httpx
            # transport error is a connection/timeout description, not
            # response content that could carry recipient data back.
            log.warning("email_send_network_error", error_type=type(exc).__name__)
            return EmailSendResult(success=False, error="network_error")

        if response.status_code >= 400:
            # Resend's error body may echo request fields back (including
            # the recipient) — never log response.text; log only the status.
            log.warning("email_send_provider_error", status_code=response.status_code)
            return EmailSendResult(success=False, error=f"provider_status_{response.status_code}")

        body = response.json()
        message_id = body.get("id") if isinstance(body, dict) else None
        log.info("email_sent", message_id=message_id, subject=message.subject)
        return EmailSendResult(success=True, provider_message_id=message_id)

    async def aclose(self) -> None:
        await self._transport.aclose()
