"""Provider configuration models — F-028."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class SecretReference(BaseModel):
    """Reference to a secret stored externally — never the secret value itself."""

    model_config = {"frozen": True}

    secret_store: str = "env"  # noqa: S105 — this is the store name, not a secret value
    secret_key: str

    def __repr__(self) -> str:
        return f"SecretReference(secret_store={self.secret_store!r}, secret_key=<redacted>)"


class ProviderConfig(BaseModel):
    provider_type: str
    display_name: str
    api_key_ref: SecretReference | None = None
    base_url: str | None = None
    timeout_seconds: float = 30.0
    extra: dict[str, Any] = Field(default_factory=dict)
    config_version: int = 1

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


class OpenRouterConfig(ProviderConfig):
    provider_type: str = "openrouter"
    base_url: str | None = "https://openrouter.ai/api/v1"
    http_referer: str | None = None
    x_title: str | None = None


class OllamaConfig(ProviderConfig):
    provider_type: str = "ollama"
    base_url: str = "http://localhost:11434"
    requires_api_key: bool = False

    @model_validator(mode="after")
    def _ollama_no_key_required(self) -> OllamaConfig:
        return self
