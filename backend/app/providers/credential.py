"""Credential validation and secret resolution — F-036.

SecretResolver
--------------
Resolves a SecretReference to its actual value at runtime.  EP-07 supports
only the ``env`` secret store; Vault and AWS Secrets Manager are reserved
for EP-09+.

CredentialValidator
-------------------
Validates API key format (prefix + minimum length) before any network call
is made.  This gives fast, clear error messages for obviously wrong keys
without leaking the key value in error messages or logs.
"""

from __future__ import annotations

import os

from app.providers.config import SecretReference, SecretStoreType
from app.providers.errors import AuthenticationError, InvalidRequestError

# ── Secret resolution ─────────────────────────────────────────────────────────


class SecretResolver:
    """Resolve a SecretReference to a plaintext value.

    The resolved value is held only in memory for the duration of a single
    request and is never written to logs, config files, or error messages.
    """

    @staticmethod
    def resolve(ref: SecretReference, *, provider_type: str) -> str:
        """Return the secret value for *ref* or raise AuthenticationError."""
        if ref.secret_store == SecretStoreType.ENV:
            value = os.environ.get(ref.secret_key, "")
            if not value:
                raise AuthenticationError(
                    f"Environment variable {ref.secret_key!r} is not set or empty. "
                    f"Set it before connecting to the {provider_type} provider.",
                    provider_type=provider_type,
                )
            return value

        # Future: Vault, AWS Secrets Manager
        raise AuthenticationError(
            f"Secret store {ref.secret_store!r} is not supported in EP-07. "
            "Only 'env' is currently supported.",
            provider_type=provider_type,
        )


# ── Credential format validation ──────────────────────────────────────────────


class CredentialValidator:
    """Validate API key format without making network calls.

    Checks only:
    1. Key prefix (provider-specific)
    2. Minimum length (guards against obviously truncated keys)

    Does NOT validate the key against the provider API — that is done by
    verify_auth().  Does NOT log or include the key value in any exception.
    """

    # OpenAI keys: "sk-..." (legacy) or "sk-proj-..." (project keys)
    _OPENAI_PREFIXES = ("sk-proj-", "sk-")
    _OPENAI_MIN_LEN = 20

    # Anthropic keys: "sk-ant-..."
    _ANTHROPIC_PREFIX = "sk-ant-"
    _ANTHROPIC_MIN_LEN = 20

    @classmethod
    def validate_openai_key(cls, key: str) -> None:
        """Raise InvalidRequestError if *key* does not look like an OpenAI key."""
        if not any(key.startswith(p) for p in cls._OPENAI_PREFIXES):
            raise InvalidRequestError(
                "Invalid OpenAI API key format — key must start with 'sk-'",
                provider_type="openai",
            )
        if len(key) < cls._OPENAI_MIN_LEN:
            raise InvalidRequestError(
                "Invalid OpenAI API key — key is too short",
                provider_type="openai",
            )

    @classmethod
    def validate_anthropic_key(cls, key: str) -> None:
        """Raise InvalidRequestError if *key* does not look like an Anthropic key."""
        if not key.startswith(cls._ANTHROPIC_PREFIX):
            raise InvalidRequestError(
                "Invalid Anthropic API key format — key must start with 'sk-ant-'",
                provider_type="anthropic",
            )
        if len(key) < cls._ANTHROPIC_MIN_LEN:
            raise InvalidRequestError(
                "Invalid Anthropic API key — key is too short",
                provider_type="anthropic",
            )
