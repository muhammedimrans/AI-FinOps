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
        if ref.secret_store == SecretStoreType.INLINE:
            # EP-22: already-decrypted value, constructed only by
            # ProviderValidator for the lifetime of a single validation call.
            if not ref.lookup_key:
                raise AuthenticationError(
                    "No credential provided for validation.", provider_type=provider_type
                )
            return ref.lookup_key

        if ref.secret_store == SecretStoreType.ENV:
            value = os.environ.get(ref.lookup_key, "")
            if not value:
                raise AuthenticationError(
                    f"Environment variable {ref.lookup_key!r} is not set or empty. "
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

    # Grok (xAI) keys: "xai-..."
    _GROK_PREFIX = "xai-"
    _GROK_MIN_LEN = 16

    # OpenRouter keys: "sk-or-v1-..."
    _OPENROUTER_PREFIX = "sk-or-"
    _OPENROUTER_MIN_LEN = 16

    # Google Gemini API keys have no single stable prefix across key types
    # (AI Studio keys are "AIza..." but service-account/OAuth flows differ) —
    # length is the only format check we can make without false-rejecting
    # valid keys.
    _GOOGLE_MIN_LEN = 20

    # Azure OpenAI resource keys are opaque 32-character hex strings, no prefix.
    _AZURE_MIN_LEN = 20

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

    @classmethod
    def validate_grok_key(cls, key: str) -> None:
        """Raise InvalidRequestError if *key* does not look like a Grok (xAI) key."""
        if not key.startswith(cls._GROK_PREFIX):
            raise InvalidRequestError(
                "Invalid Grok API key format — key must start with 'xai-'",
                provider_type="grok",
            )
        if len(key) < cls._GROK_MIN_LEN:
            raise InvalidRequestError(
                "Invalid Grok API key — key is too short",
                provider_type="grok",
            )

    @classmethod
    def validate_openrouter_key(cls, key: str) -> None:
        """Raise InvalidRequestError if *key* does not look like an OpenRouter key."""
        if not key.startswith(cls._OPENROUTER_PREFIX):
            raise InvalidRequestError(
                "Invalid OpenRouter API key format — key must start with 'sk-or-'",
                provider_type="openrouter",
            )
        if len(key) < cls._OPENROUTER_MIN_LEN:
            raise InvalidRequestError(
                "Invalid OpenRouter API key — key is too short",
                provider_type="openrouter",
            )

    @classmethod
    def validate_google_key(cls, key: str) -> None:
        """Raise InvalidRequestError if *key* is too short to be a Google API key."""
        if len(key) < cls._GOOGLE_MIN_LEN:
            raise InvalidRequestError(
                "Invalid Google API key — key is too short",
                provider_type="google",
            )

    @classmethod
    def validate_azure_key(cls, key: str) -> None:
        """Raise InvalidRequestError if *key* is too short to be an Azure OpenAI key."""
        if len(key) < cls._AZURE_MIN_LEN:
            raise InvalidRequestError(
                "Invalid Azure OpenAI API key — key is too short",
                provider_type="azure_openai",
            )
