"""EmailTemplateRenderer — rendering only, EP-24.4.

Responsible only for turning (template name, context) into HTML + plain
text. No HTTP logic (that's ``EmailProvider``), no authentication logic
(that's ``AuthService``/``EmailService``) — a renderer instance is pure,
side-effect-free, and safe to unit test without a database or network.

No third-party template engine is introduced: three templates sharing one
layout doesn't justify a new dependency (Jinja2 et al.), and Python's own
``str.format`` plus a small HTML-escaping helper covers this cleanly. All
user-controlled values (display name) are escaped before interpolation —
the token/URL values are not (they're server-generated, never
user-supplied).
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape

_BRAND_TEAL = "#14D9D3"
_BRAND_MINT = "#7AF7E8"


@dataclass(frozen=True, slots=True)
class RenderedEmail:
    subject: str
    html_body: str
    text_body: str


def _layout(*, preheader: str, body_html: str) -> str:
    """Shared responsive, dark-mode-aware HTML shell every template renders into.

    ``prefers-color-scheme`` media query + ``[data-ogsc]``/``[data-ogsb]``
    attribute overrides cover the two dominant email-client dark-mode
    strategies (native OS-level, and Outlook/Gmail's own re-coloring hooks)
    without any client-side script — email clients strip <script> anyway.
    """
    return f"""<!DOCTYPE html>
<html lang="en" xmlns="http://www.w3.org/1999/xhtml">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="X-UA-Compatible" content="IE=edge">
<meta name="color-scheme" content="light dark">
<meta name="supported-color-schemes" content="light dark">
<title>Costorah</title>
<style>
  body, table, td, a {{ -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%; }}
  table, td {{ mso-table-lspace: 0pt; mso-table-rspace: 0pt; }}
  img {{ -ms-interpolation-mode: bicubic; border: 0; height: auto; line-height: 100%; outline: none; text-decoration: none; }}
  body {{ margin: 0; padding: 0; width: 100% !important; height: 100% !important; background-color: #f4f5f7; }}
  .email-bg {{ background-color: #f4f5f7; }}
  .card {{ background-color: #ffffff; }}
  .heading {{ color: #0f1115; }}
  .body-text {{ color: #4b5160; }}
  .muted {{ color: #8a8f9c; }}
  .divider {{ border-top: 1px solid #e6e8ec; }}
  @media (prefers-color-scheme: dark) {{
    .email-bg {{ background-color: #0b0d10 !important; }}
    .card {{ background-color: #14171c !important; }}
    .heading {{ color: #f5f6f8 !important; }}
    .body-text {{ color: #c3c7d1 !important; }}
    .muted {{ color: #7d828f !important; }}
    .divider {{ border-top: 1px solid #262a31 !important; }}
  }}
  [data-ogsc] .email-bg {{ background-color: #0b0d10 !important; }}
  [data-ogsc] .card {{ background-color: #14171c !important; }}
  [data-ogsc] .heading {{ color: #f5f6f8 !important; }}
  [data-ogsc] .body-text {{ color: #c3c7d1 !important; }}
  [data-ogsc] .muted {{ color: #7d828f !important; }}
  @media only screen and (max-width: 600px) {{
    .container {{ width: 100% !important; }}
    .px-32 {{ padding-left: 20px !important; padding-right: 20px !important; }}
  }}
</style>
</head>
<body class="email-bg" style="margin:0;padding:0;">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;">{escape(preheader)}&#8202;&#8202;&#8202;&#8202;&#8202;&#8202;&#8202;&#8202;&#8202;&#8202;&#8202;&#8202;&#8202;&#8202;&#8202;&#8202;&#8202;&#8202;&#8202;&#8202;</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="email-bg">
<tr><td align="center" style="padding:32px 16px;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" class="container" style="width:600px;max-width:100%;">
<tr><td align="center" style="padding-bottom:24px;">
<span style="font-family:'Segoe UI',Helvetica,Arial,sans-serif;font-size:20px;font-weight:700;color:{_BRAND_TEAL};letter-spacing:-0.02em;">Costorah</span>
</td></tr>
<tr><td class="card" style="border-radius:16px;overflow:hidden;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0">
<tr><td class="px-32" style="padding:40px 40px 32px 40px;font-family:'Segoe UI',Helvetica,Arial,sans-serif;">
{body_html}
</td></tr>
</table>
</td></tr>
<tr><td align="center" class="px-32" style="padding:28px 24px 0 24px;font-family:'Segoe UI',Helvetica,Arial,sans-serif;">
<p class="muted" style="margin:0 0 6px 0;font-size:12px;line-height:18px;">
Need help? Contact us at <a href="mailto:support@costorah.com" style="color:{_BRAND_TEAL};text-decoration:none;">support@costorah.com</a>
</p>
<p class="muted" style="margin:0;font-size:12px;line-height:18px;">
&copy; {{year}} Costorah. All rights reserved.
</p>
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""


def _button(*, url: str, label: str) -> str:
    return f"""<table role="presentation" cellpadding="0" cellspacing="0" style="margin:28px 0;">
<tr><td style="border-radius:10px;background-color:{_BRAND_TEAL};">
<a href="{url}" target="_blank" rel="noopener noreferrer"
   style="display:inline-block;padding:13px 28px;font-family:'Segoe UI',Helvetica,Arial,sans-serif;
          font-size:14px;font-weight:600;color:#04211f;text-decoration:none;border-radius:10px;">
  {escape(label)}
</a>
</td></tr>
</table>"""


def _fallback_url_block(url: str) -> str:
    return f"""<p class="body-text" style="margin:20px 0 0 0;font-size:12px;line-height:20px;">
If the button above doesn't work, copy and paste this link into your browser:<br>
<a href="{url}" target="_blank" rel="noopener noreferrer" style="color:{_BRAND_TEAL};word-break:break-all;">{escape(url)}</a>
</p>"""


class EmailTemplateRenderer:
    """Renders the fixed set of transactional email templates this EP defines.

    Every render method is a pure function of its arguments — no I/O, no
    settings/config access (URLs and expiry copy are passed in by the
    caller, ``EmailService``, which is the layer that knows about
    ``Settings``).
    """

    def render_verification_email(
        self,
        *,
        display_name: str,
        verify_url: str,
        expires_hours: int,
        year: int,
    ) -> RenderedEmail:
        name = escape(display_name)
        body_html = f"""
<h1 class="heading" style="margin:0 0 16px 0;font-size:22px;line-height:30px;font-weight:700;">Welcome to Costorah</h1>
<p class="body-text" style="margin:0;font-size:14px;line-height:22px;">Hi {name},</p>
<p class="body-text" style="margin:12px 0 0 0;font-size:14px;line-height:22px;">
Thanks for creating a Costorah account. Confirm your email address to finish setting up your workspace.
</p>
{_button(url=verify_url, label="Verify email")}
<p class="body-text" style="margin:0;font-size:13px;line-height:20px;">
This link expires in {expires_hours} hours. If you didn't create a Costorah account, you can safely ignore this email.
</p>
{_fallback_url_block(verify_url)}
"""
        html = _layout(
            preheader="Confirm your email address to finish setting up Costorah.",
            body_html=body_html,
        ).replace("{year}", str(year))
        text = (
            f"Welcome to Costorah\n\n"
            f"Hi {display_name},\n\n"
            f"Thanks for creating a Costorah account. Confirm your email address to finish "
            f"setting up your workspace by visiting the link below:\n\n"
            f"{verify_url}\n\n"
            f"This link expires in {expires_hours} hours. If you didn't create a Costorah "
            f"account, you can safely ignore this email.\n\n"
            f"Need help? Contact support@costorah.com"
        )
        return RenderedEmail(subject="Verify your email address", html_body=html, text_body=text)

    def render_welcome_email(
        self,
        *,
        display_name: str,
        dashboard_url: str,
        year: int,
    ) -> RenderedEmail:
        name = escape(display_name)
        body_html = f"""
<h1 class="heading" style="margin:0 0 16px 0;font-size:22px;line-height:30px;font-weight:700;">You're all set, {name}</h1>
<p class="body-text" style="margin:0;font-size:14px;line-height:22px;">
Your email is confirmed and your Costorah workspace is ready. Connect a provider to start tracking AI spend in real time.
</p>
{_button(url=dashboard_url, label="Go to dashboard")}
<p class="body-text" style="margin:0;font-size:13px;line-height:20px;">
Costorah gives you cost observability across every AI provider you use — usage, budgets, and alerts, all in one place.
</p>
"""
        html = _layout(
            preheader="Your Costorah workspace is ready.",
            body_html=body_html,
        ).replace("{year}", str(year))
        text = (
            f"You're all set, {display_name}\n\n"
            f"Your email is confirmed and your Costorah workspace is ready. Connect a "
            f"provider to start tracking AI spend in real time:\n\n"
            f"{dashboard_url}\n\n"
            f"Need help? Contact support@costorah.com"
        )
        return RenderedEmail(subject="Welcome to Costorah", html_body=html, text_body=text)

    def render_password_reset_email(
        self,
        *,
        display_name: str,
        reset_url: str,
        expires_hours: int,
        year: int,
    ) -> RenderedEmail:
        name = escape(display_name)
        body_html = f"""
<h1 class="heading" style="margin:0 0 16px 0;font-size:22px;line-height:30px;font-weight:700;">Reset your password</h1>
<p class="body-text" style="margin:0;font-size:14px;line-height:22px;">Hi {name},</p>
<p class="body-text" style="margin:12px 0 0 0;font-size:14px;line-height:22px;">
We received a request to reset the password for your Costorah account. Click below to choose a new one.
</p>
{_button(url=reset_url, label="Reset password")}
<p class="body-text" style="margin:0;font-size:13px;line-height:20px;">
This link expires in {expires_hours} hour{"s" if expires_hours != 1 else ""} and can only be used once.
If you didn't request this, you can safely ignore this email — your password will not change.
</p>
{_fallback_url_block(reset_url)}
"""
        html = _layout(
            preheader="Reset the password for your Costorah account.",
            body_html=body_html,
        ).replace("{year}", str(year))
        text = (
            f"Reset your password\n\n"
            f"Hi {display_name},\n\n"
            f"We received a request to reset the password for your Costorah account. "
            f"Visit the link below to choose a new one:\n\n"
            f"{reset_url}\n\n"
            f"This link expires in {expires_hours} hour{'s' if expires_hours != 1 else ''} and can "
            f"only be used once. If you didn't request this, you can safely ignore this "
            f"email — your password will not change.\n\n"
            f"Need help? Contact support@costorah.com"
        )
        return RenderedEmail(subject="Reset your Costorah password", html_body=html, text_body=text)

    # ── Organization invitations (EP-24.6) ──────────────────────────────────

    def render_invitation_email(
        self,
        *,
        organization_name: str,
        inviter_name: str,
        role: str,
        accept_url: str,
        expires_at_display: str,
        year: int,
    ) -> RenderedEmail:
        org = escape(organization_name)
        inviter = escape(inviter_name)
        role_label = escape(role.capitalize())
        expires = escape(expires_at_display)
        body_html = f"""
<h1 class="heading" style="margin:0 0 16px 0;font-size:22px;line-height:30px;font-weight:700;">You're invited to join {org}</h1>
<p class="body-text" style="margin:0;font-size:14px;line-height:22px;">
{inviter} has invited you to join <strong>{org}</strong> on Costorah as <strong>{role_label}</strong>.
</p>
{_button(url=accept_url, label="Accept invitation")}
<p class="body-text" style="margin:0;font-size:13px;line-height:20px;">
This invitation expires on {expires}. If you weren't expecting this, you can safely ignore this email.
</p>
{_fallback_url_block(accept_url)}
"""
        html = _layout(
            preheader=f"{inviter} invited you to join {organization_name} on Costorah.",
            body_html=body_html,
        ).replace("{year}", str(year))
        text = (
            f"You're invited to join {organization_name}\n\n"
            f"{inviter_name} has invited you to join {organization_name} on Costorah as {role.capitalize()}.\n\n"
            f"Accept your invitation:\n\n"
            f"{accept_url}\n\n"
            f"This invitation expires on {expires_at_display}. If you weren't expecting this, "
            f"you can safely ignore this email.\n\n"
            f"Need help? Contact support@costorah.com"
        )
        return RenderedEmail(
            subject=f"You're invited to join {organization_name} on Costorah",
            html_body=html,
            text_body=text,
        )

    def render_invitation_accepted_email(
        self,
        *,
        organization_name: str,
        member_email: str,
        role: str,
        members_url: str,
        year: int,
    ) -> RenderedEmail:
        org = escape(organization_name)
        member = escape(member_email)
        role_label = escape(role.capitalize())
        body_html = f"""
<h1 class="heading" style="margin:0 0 16px 0;font-size:22px;line-height:30px;font-weight:700;">{member} joined {org}</h1>
<p class="body-text" style="margin:0;font-size:14px;line-height:22px;">
Your invitation was accepted — {member} is now a <strong>{role_label}</strong> of {org}.
</p>
{_button(url=members_url, label="View members")}
"""
        html = _layout(
            preheader=f"{member_email} accepted your invitation to {organization_name}.",
            body_html=body_html,
        ).replace("{year}", str(year))
        text = (
            f"{member_email} joined {organization_name}\n\n"
            f"Your invitation was accepted — {member_email} is now a {role.capitalize()} of "
            f"{organization_name}.\n\n"
            f"View members:\n\n"
            f"{members_url}\n\n"
            f"Need help? Contact support@costorah.com"
        )
        return RenderedEmail(
            subject=f"{member_email} joined {organization_name}", html_body=html, text_body=text
        )

    def render_invitation_cancelled_email(
        self,
        *,
        organization_name: str,
        year: int,
    ) -> RenderedEmail:
        org = escape(organization_name)
        body_html = f"""
<h1 class="heading" style="margin:0 0 16px 0;font-size:22px;line-height:30px;font-weight:700;">Invitation cancelled</h1>
<p class="body-text" style="margin:0;font-size:14px;line-height:22px;">
Your invitation to join <strong>{org}</strong> on Costorah has been cancelled. If you believe this was a mistake, contact the workspace's admin to request a new invitation.
</p>
"""
        html = _layout(
            preheader=f"Your invitation to join {organization_name} was cancelled.",
            body_html=body_html,
        ).replace("{year}", str(year))
        text = (
            f"Invitation cancelled\n\n"
            f"Your invitation to join {organization_name} on Costorah has been cancelled. "
            f"If you believe this was a mistake, contact the workspace's admin to request a "
            f"new invitation.\n\n"
            f"Need help? Contact support@costorah.com"
        )
        return RenderedEmail(
            subject=f"Your invitation to {organization_name} was cancelled",
            html_body=html,
            text_body=text,
        )
