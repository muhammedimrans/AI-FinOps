"""Browser-session cookies — EP-21.2 / ADR-006.

Additive to the existing bearer-token flow, not a replacement: login,
register, and refresh continue to return tokens in the JSON body
(`TokenResponse`) exactly as before — `apps/dashboard` keeps working
unmodified. These two httpOnly cookies are set on the same responses
so a browser-based client (`apps/website`, and eventually
`apps/dashboard` once it migrates to `credentials: "include"`) can
rely on the cookie instead of managing tokens in JS.

`get_current_user` (`app/auth/dependencies.py`) reads the access-token
cookie as a fallback when no `Authorization` header is present, so
either mechanism authenticates the same set of endpoints.
"""

from __future__ import annotations

from fastapi import Response

from app.auth.service import TokenPair
from app.config.settings import Settings

ACCESS_TOKEN_COOKIE = "costorah_access_token"  # noqa: S105
REFRESH_TOKEN_COOKIE = "costorah_refresh_token"  # noqa: S105


def set_session_cookies(response: Response, pair: TokenPair, settings: Settings) -> None:
    """Set the access + refresh token cookies on a login/register/refresh response."""
    secure = settings.is_production
    refresh_max_age = settings.jwt_refresh_token_expire_days * 24 * 60 * 60

    response.set_cookie(
        ACCESS_TOKEN_COOKIE,
        pair.access_token,
        max_age=pair.expires_in,
        httponly=True,
        secure=secure,
        samesite="lax",
        domain=settings.session_cookie_domain,
        path="/",
    )
    response.set_cookie(
        REFRESH_TOKEN_COOKIE,
        pair.refresh_token,
        max_age=refresh_max_age,
        httponly=True,
        secure=secure,
        samesite="lax",
        domain=settings.session_cookie_domain,
        path="/",
    )


def clear_session_cookies(response: Response, settings: Settings) -> None:
    """Clear both session cookies on logout."""
    response.delete_cookie(ACCESS_TOKEN_COOKIE, domain=settings.session_cookie_domain, path="/")
    response.delete_cookie(REFRESH_TOKEN_COOKIE, domain=settings.session_cookie_domain, path="/")
