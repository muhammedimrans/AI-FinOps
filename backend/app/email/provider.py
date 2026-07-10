"""EmailProvider — transport abstraction for outbound email (EP-24.4).

Every concrete provider (Resend today; Amazon SES, SendGrid, Mailgun, or
Postmark later) implements this one interface. Nothing above this layer
(``EmailService``, and by extension every authentication/notification code
path) ever depends on a provider-specific detail — only on
``EmailMessage``/``EmailSendResult`` and ``send_email()``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class EmailMessage:
    """A fully-rendered, provider-agnostic email ready to send.

    ``html_body``/``text_body`` are already-rendered content — rendering is
    ``EmailTemplateRenderer``'s job, never a provider's.
    """

    to: str
    subject: str
    html_body: str
    text_body: str
    reply_to: str | None = None
    tags: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EmailSendResult:
    """Outcome of one ``send_email()`` call.

    ``skipped`` (not ``success=False``) is the outcome when the provider has
    no credentials configured — the caller (``EmailService``) logs this as a
    non-fatal, expected condition in any environment that hasn't provisioned
    ``RESEND_API_KEY`` (local dev, CI, most of the test suite), rather than
    raising and breaking the calling flow (registration, password reset,
    ...) over an email that was never going to be deliverable anyway.
    """

    success: bool
    skipped: bool = False
    provider_message_id: str | None = None
    error: str | None = None


class EmailProvider(ABC):
    """Abstract transport for sending one already-rendered email."""

    @abstractmethod
    async def send_email(self, message: EmailMessage) -> EmailSendResult:
        """Send ``message``. Must never raise for an ordinary delivery
        failure (invalid recipient, provider outage, etc.) — those are
        reported via ``EmailSendResult.success=False`` so a failed email
        never turns into an unhandled 500 for the caller's own operation
        (e.g. registration must still succeed even if the welcome email
        can't be delivered). Only a programming error should raise."""
        raise NotImplementedError
