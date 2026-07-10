"""EmailService — business logic for what Costorah sends, EP-24.4.

Authentication (and any future) services depend on this class only, never
on ``ResendEmailProvider``/``EmailTemplateRenderer`` directly. This is the
one seam a new transactional email (budget alerts, usage alerts, invoices,
organization invites, generic notifications — all named as "future-ready"
targets in this EP's brief) is added at: one new ``send_*`` method here,
reusing the existing ``EmailProvider``/``EmailTemplateRenderer`` layers,
never a second email pipeline.
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog

from app.config.settings import Settings
from app.email.provider import EmailMessage, EmailProvider, EmailSendResult
from app.email.renderer import EmailTemplateRenderer, RenderedEmail
from app.email.resend_provider import ResendEmailProvider

log = structlog.get_logger(__name__)


class EmailService:
    """Sends Costorah's transactional emails.

    Constructed from ``Settings`` by default (``provider``/``renderer`` are
    optional overrides, used by tests to inject a mock provider) — mirrors
    the optional-constructor-injection pattern already established by
    ``ProviderSyncService``/``BudgetEvaluationService`` elsewhere in this
    codebase, so callers that only ever need the default (every real
    request) don't have to wire anything, while tests can substitute a
    fake provider without any DI container changes.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        provider: EmailProvider | None = None,
        renderer: EmailTemplateRenderer | None = None,
    ) -> None:
        self._settings = settings
        self._provider = provider or ResendEmailProvider(
            api_key=settings.resend_api_key.get_secret_value() if settings.resend_api_key else None,
            from_email=settings.email_from,
        )
        self._renderer = renderer or EmailTemplateRenderer()

    async def send_verification_email(
        self,
        *,
        to: str,
        display_name: str,
        verify_url: str,
    ) -> EmailSendResult:
        rendered = self._renderer.render_verification_email(
            display_name=display_name,
            verify_url=verify_url,
            expires_hours=24,
            year=datetime.now(UTC).year,
        )
        return await self._send(to=to, rendered=rendered, tag="verification")

    async def send_welcome_email(self, *, to: str, display_name: str) -> EmailSendResult:
        rendered = self._renderer.render_welcome_email(
            display_name=display_name,
            dashboard_url=self._settings.dashboard_url,
            year=datetime.now(UTC).year,
        )
        return await self._send(to=to, rendered=rendered, tag="welcome")

    async def send_password_reset_email(
        self,
        *,
        to: str,
        display_name: str,
        reset_url: str,
    ) -> EmailSendResult:
        rendered = self._renderer.render_password_reset_email(
            display_name=display_name,
            reset_url=reset_url,
            expires_hours=1,
            year=datetime.now(UTC).year,
        )
        return await self._send(to=to, rendered=rendered, tag="password_reset")

    # ── Organization invitations (EP-24.6) ──────────────────────────────────

    async def send_invitation_email(
        self,
        *,
        to: str,
        organization_name: str,
        inviter_name: str,
        role: str,
        accept_url: str,
        expires_at_display: str,
    ) -> EmailSendResult:
        rendered = self._renderer.render_invitation_email(
            organization_name=organization_name,
            inviter_name=inviter_name,
            role=role,
            accept_url=accept_url,
            expires_at_display=expires_at_display,
            year=datetime.now(UTC).year,
        )
        return await self._send(to=to, rendered=rendered, tag="invitation")

    async def send_invitation_accepted_email(
        self,
        *,
        to: str,
        organization_name: str,
        member_email: str,
        role: str,
    ) -> EmailSendResult:
        rendered = self._renderer.render_invitation_accepted_email(
            organization_name=organization_name,
            member_email=member_email,
            role=role,
            members_url=f"{self._settings.dashboard_url}/users",
            year=datetime.now(UTC).year,
        )
        return await self._send(to=to, rendered=rendered, tag="invitation_accepted")

    async def send_invitation_cancelled_email(
        self,
        *,
        to: str,
        organization_name: str,
    ) -> EmailSendResult:
        rendered = self._renderer.render_invitation_cancelled_email(
            organization_name=organization_name,
            year=datetime.now(UTC).year,
        )
        return await self._send(to=to, rendered=rendered, tag="invitation_cancelled")

    async def _send(self, *, to: str, rendered: RenderedEmail, tag: str) -> EmailSendResult:
        message = EmailMessage(
            to=to,
            subject=rendered.subject,
            html_body=rendered.html_body,
            text_body=rendered.text_body,
            tags={"category": tag},
        )
        result = await self._provider.send_email(message)
        if not result.success and not result.skipped:
            log.warning("email_delivery_failed", tag=tag, error=result.error)
        return result

    async def aclose(self) -> None:
        aclose = getattr(self._provider, "aclose", None)
        if aclose is not None:
            await aclose()
