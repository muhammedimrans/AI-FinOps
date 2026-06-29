"""JWT access-token issuance / validation and opaque refresh-token utilities — EP-05 / F-017."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from jwt.exceptions import DecodeError, ExpiredSignatureError, InvalidTokenError

from app.config.settings import Settings, get_settings


def create_access_token(
    *,
    user_id: str,
    session_id: str,
    email: str,
    settings: Settings | None = None,
) -> str:
    """Return a signed HS256 JWT access token."""
    s = settings or get_settings()
    now = datetime.now(UTC)
    exp = now + timedelta(minutes=s.jwt_access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": user_id,
        "jti": session_id,
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "type": "access",
    }
    secret = s.jwt_secret.get_secret_value()
    return jwt.encode(payload, secret, algorithm=s.jwt_algorithm)


def decode_access_token(
    token: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """
    Decode and validate an HS256 access token.

    Re-raises jwt.exceptions.ExpiredSignatureError, DecodeError, or
    InvalidTokenError on any validation failure — callers convert to HTTP 401.
    """
    s = settings or get_settings()
    secret = s.jwt_secret.get_secret_value()
    payload: dict[str, Any] = jwt.decode(
        token,
        secret,
        algorithms=[s.jwt_algorithm],
    )
    if payload.get("type") != "access":
        raise InvalidTokenError("Token type mismatch")
    return payload


def generate_refresh_token() -> str:
    """Return a 256-bit URL-safe opaque refresh token."""
    return secrets.token_urlsafe(32)


def hash_token(raw: str) -> str:
    """Return the SHA-256 hex digest of a raw token for safe storage."""
    return hashlib.sha256(raw.encode()).hexdigest()


__all__ = [
    "DecodeError",
    "ExpiredSignatureError",
    "InvalidTokenError",
    "create_access_token",
    "decode_access_token",
    "generate_refresh_token",
    "hash_token",
]
