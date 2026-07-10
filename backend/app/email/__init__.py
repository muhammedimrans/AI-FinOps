"""Reusable transactional email infrastructure — EP-24.4.

Layering (each layer depends only on the one below it):

    EmailService            business logic — what to send, never how
        -> EmailTemplateRenderer   HTML/text rendering, no HTTP/auth logic
        -> EmailProvider           transport abstraction
              -> ResendEmailProvider   the one concrete implementation today

Authentication (and any future) services call ``EmailService`` only — never
``ResendEmailProvider``/Resend's API directly. Swapping providers (Amazon
SES, SendGrid, Mailgun, Postmark) means writing one new ``EmailProvider``
subclass and changing ``EmailService``'s construction, not touching any
caller.
"""

from __future__ import annotations
