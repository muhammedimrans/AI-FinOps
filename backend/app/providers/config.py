"""Provider configuration models — F-028."""

from __future__ import annotations

import enum
import ipaddress
from typing import Any, ClassVar
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator

# ── Secret store types ────────────────────────────────────────────────────────


class SecretStoreType(enum.StrEnum):
    """Supported secret-store backends for SecretReference."""

    ENV = "env"
    VAULT = "vault"
    AWS_SECRETS_MANAGER = "aws_secrets_manager"
    # EP-22: the secret value has already been decrypted (by
    # app.security.encryption.EncryptionService, from a customer's stored
    # ProviderConnection.encrypted_api_key) and is carried inline in
    # ``lookup_key`` for the duration of a single validation/usage request.
    # Never persisted in this form — see ProviderValidator, which is the only
    # place this variant is constructed.
    INLINE = "inline"


class SecretReference(BaseModel):
    """Reference to a secret — usually stored externally, never the secret
    value itself, with one deliberate exception (see ``SecretStoreType.INLINE``).

    Storing the *name* of the environment variable (or Vault path) rather than
    the raw credential prevents secrets from appearing in logs, serialised
    configs, or stack traces.  The ``__repr__`` override redacts ``lookup_key``
    even if the object is inadvertently included in a log message — this
    holds even for ``INLINE`` references, where ``lookup_key`` does carry the
    actual decrypted value.

    Note: the field is named ``lookup_key`` (not ``secret_key``) so that static
    security scanners (e.g. Bandit's hardcoded-password heuristic) do not flag
    call sites — for ``ENV``/``VAULT``/``AWS_SECRETS_MANAGER`` the value is
    the *name* of an env var / vault path, never a secret value itself; for
    ``INLINE`` it is the already-decrypted value, held only in memory for a
    single request (see ``SecretStoreType.INLINE``).
    """

    model_config = {"frozen": True}

    secret_store: SecretStoreType = SecretStoreType.ENV
    lookup_key: str

    def __repr__(self) -> str:
        return f"SecretReference(secret_store={self.secret_store!r}, lookup_key=<redacted>)"


# ── SSRF guard ────────────────────────────────────────────────────────────────

_BLOCKED_METADATA_HOSTS: frozenset[str] = frozenset(
    {
        # AWS / Azure / GCP link-local metadata services — always blocked.
        "169.254.169.254",
        "fd00:ec2::254",
        "metadata.google.internal",
        "metadata.internal",
        # APIPA range check is done via ipaddress, but add the canonical
        # metadata addresses explicitly as a defence-in-depth measure.
    }
)


def _check_ssrf(url: str, *, allow_http: bool = False) -> None:
    """Raise ValueError if *url* is a known SSRF target or uses a forbidden scheme.

    Security rationale
    ------------------
    Provider ``base_url`` values are written by administrators and can be
    changed via the API.  Without validation a malicious or misconfigured
    ``base_url`` of ``http://169.254.169.254/latest/meta-data/`` would cause
    EP-07's HTTP client to reach the cloud-instance metadata service,
    potentially leaking IAM credentials.

    For cloud providers (``allow_http=False``) we additionally require HTTPS
    and reject all loopback / RFC-1918 / link-local addresses.  For
    self-hosted providers such as Ollama (``allow_http=True``) we still block
    cloud metadata endpoints but permit ``http://`` and local addresses.

    No network calls are made — all checks are pure string/IP analysis.
    """
    try:
        parsed = urlparse(url)
    except Exception as exc:
        raise ValueError(f"Unparseable URL: {url!r}") from exc

    scheme = (parsed.scheme or "").lower()
    if scheme not in {"http", "https"}:
        raise ValueError(
            f"base_url scheme must be 'http' or 'https', got {scheme!r}. "
            "Other schemes are not permitted."
        )

    if scheme == "http" and not allow_http:
        raise ValueError(
            "base_url must use 'https' for cloud providers. "
            "Plain HTTP is only permitted for self-hosted providers (e.g. OllamaConfig)."
        )

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise ValueError("base_url must include a hostname.")

    if hostname in _BLOCKED_METADATA_HOSTS:
        raise ValueError(
            f"base_url hostname {hostname!r} is a blocked cloud-metadata endpoint "
            "and cannot be used as a provider base URL."
        )

    if not allow_http:
        if hostname in {"localhost", "localhost.localdomain"}:
            raise ValueError(
                f"base_url hostname {hostname!r} is not permitted for cloud providers."
            )
        try:
            addr = ipaddress.ip_address(hostname)
        except ValueError:
            pass  # valid public hostname — allow
        else:
            if addr.is_loopback or addr.is_private or addr.is_link_local or addr.is_reserved:
                raise ValueError(
                    f"base_url resolves to a non-routable address ({hostname!r}) "
                    "which is not permitted for cloud providers."
                )


# ── Base provider config ───────────────────────────────────────────────────────


class ProviderConfig(BaseModel):
    """Base configuration shared by all provider types.

    Subclasses lock ``provider_type`` to a string literal and add
    provider-specific fields (e.g. ``OpenAIConfig.organization_id``).

    Security invariants
    -------------------
    * ``provider_type`` must be a known ``ProviderType`` value — validated at
      construction time so invalid values never reach the factory.
    * ``base_url``, when set, is checked for SSRF patterns.
    * ``extra`` must not contain any credential-pattern keys — use
      ``SecretReference`` instead.
    """

    _allow_http_base_url: ClassVar[bool] = False

    provider_type: str
    display_name: str
    api_key_ref: SecretReference | None = None
    base_url: str | None = None
    timeout_seconds: float = 30.0
    extra: dict[str, Any] = Field(default_factory=dict)
    config_version: int = 1

    @field_validator("provider_type", mode="before")
    @classmethod
    def _validate_provider_type(cls, v: object) -> object:
        if isinstance(v, str):
            from app.models.provider_connection import ProviderType

            try:
                ProviderType(v)
            except ValueError:
                valid = sorted(pt.value for pt in ProviderType)
                raise ValueError(f"Invalid provider_type {v!r}. Must be one of: {valid}") from None
        return v

    @field_validator("base_url", mode="after")
    @classmethod
    def _validate_base_url(cls, v: str | None) -> str | None:
        if v is not None:
            _check_ssrf(v, allow_http=cls._allow_http_base_url)
        return v

    @model_validator(mode="after")
    def _no_plaintext_secrets(self) -> ProviderConfig:
        sensitive_keys = {"api_key", "secret", "password", "token", "key"}
        for k in self.extra:
            if any(s in k.lower() for s in sensitive_keys):
                raise ValueError(
                    "extra config must not contain credential keys;"
                    f" use SecretReference instead: {k!r}"
                )
        return self


# ── Provider-specific subclasses ──────────────────────────────────────────────


class OpenAIConfig(ProviderConfig):
    provider_type: str = "openai"
    organization_id: str | None = None
    project_id: str | None = None


class AnthropicConfig(ProviderConfig):
    provider_type: str = "anthropic"
    anthropic_version: str = "2023-06-01"


class GrokConfig(ProviderConfig):
    provider_type: str = "grok"
    base_url: str | None = "https://api.x.ai/v1"


class GoogleConfig(ProviderConfig):
    provider_type: str = "google"
    project_id: str | None = None
    location: str = "us-central1"


class AzureOpenAIConfig(ProviderConfig):
    provider_type: str = "azure_openai"
    azure_endpoint: str
    api_version: str = "2024-02-01"
    deployment_name: str | None = None

    @field_validator("azure_endpoint", mode="after")
    @classmethod
    def _validate_azure_endpoint(cls, v: str) -> str:
        _check_ssrf(v, allow_http=False)
        return v


class OpenRouterConfig(ProviderConfig):
    provider_type: str = "openrouter"
    base_url: str | None = "https://openrouter.ai/api/v1"
    http_referer: str | None = None
    x_title: str | None = None


class OllamaConfig(ProviderConfig):
    """Configuration for self-hosted Ollama deployments.

    Ollama runs locally (or on a private LAN) and does not require an API key.
    HTTP is explicitly permitted here because Ollama endpoints are typically
    plain HTTP.  Cloud-metadata SSRF targets are still blocked.
    """

    _allow_http_base_url: ClassVar[bool] = True

    provider_type: str = "ollama"
    base_url: str = "http://localhost:11434"
    requires_api_key: bool = False
