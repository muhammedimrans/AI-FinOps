"""ProviderValidator — live credential validation (EP-22, Part 3).

Runs a real API call against the provider (reusing the same
``ProviderFactory`` + ``AIProvider.verify_auth()`` machinery that
``app.api.v1.providers`` already uses for the server-side-env-var probe),
then normalizes the outcome into ``ProviderValidationStatus`` — a small,
user-safe vocabulary — so raw provider error text (which can include
account IDs, billing details, or other provider-side specifics) never
reaches an API response body or a log line. See CLAUDE.md §13 for the full
validation-flow writeup and the per-provider probe-endpoint table.

Design note: no per-provider branching lives here beyond building the right
``ProviderConfig`` subclass — the actual HTTP call and error handling is
entirely inside each adapter (``verify_auth()``) and ``ProviderHttpClient``'s
existing ``map_http_error``. Adding an 8th provider means adding one more
``match`` arm to ``_build_config`` and registering its adapter in
``ProviderFactory.build_default_registry`` — no other code in this module
changes.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.provider_connection import (
    ProviderHealthStatus,
    ProviderType,
    ProviderValidationStatus,
)
from app.providers.config import (
    AnthropicConfig,
    AzureOpenAIConfig,
    GoogleConfig,
    GrokConfig,
    OllamaConfig,
    OpenAIConfig,
    OpenRouterConfig,
    ProviderConfig,
    SecretReference,
    SecretStoreType,
)
from app.providers.errors import (
    AuthenticationError,
    InternalProviderError,
    InvalidRequestError,
    NetworkError,
    ProviderError,
    QuotaExceededError,
    RateLimitError,
)
from app.providers.factory import ProviderFactory
from app.providers.registry import ProviderRegistry, get_registry

_NORMALIZED_MESSAGES: dict[ProviderValidationStatus, str] = {
    ProviderValidationStatus.HEALTHY: "Connection healthy.",
    ProviderValidationStatus.INVALID_API_KEY: "The API key is invalid or has been revoked.",
    ProviderValidationStatus.UNAUTHORIZED: (
        "The API key is valid but is not authorized for this operation."
    ),
    ProviderValidationStatus.QUOTA_EXCEEDED: (
        "The provider account has exceeded its usage quota or rate limit."
    ),
    ProviderValidationStatus.NETWORK_FAILURE: "Could not reach the provider — network error.",
    ProviderValidationStatus.TIMEOUT: "The request to the provider timed out.",
    ProviderValidationStatus.PROVIDER_UNAVAILABLE: "The provider is currently unavailable.",
}

# Coarse health_status the EP-19.3 alert engine keys off, derived from the
# finer-grained validation outcome — see ProviderValidationStatus's docstring.
_HEALTH_STATUS_FOR: dict[ProviderValidationStatus, ProviderHealthStatus] = {
    ProviderValidationStatus.HEALTHY: ProviderHealthStatus.HEALTHY,
    ProviderValidationStatus.INVALID_API_KEY: ProviderHealthStatus.CRITICAL,
    ProviderValidationStatus.UNAUTHORIZED: ProviderHealthStatus.CRITICAL,
    ProviderValidationStatus.QUOTA_EXCEEDED: ProviderHealthStatus.WARNING,
    ProviderValidationStatus.NETWORK_FAILURE: ProviderHealthStatus.WARNING,
    ProviderValidationStatus.TIMEOUT: ProviderHealthStatus.WARNING,
    ProviderValidationStatus.PROVIDER_UNAVAILABLE: ProviderHealthStatus.CRITICAL,
}


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Outcome of a single ``ProviderValidator.validate()`` call."""

    validation_status: ProviderValidationStatus
    health_status: ProviderHealthStatus
    detail: str  # normalized, user-safe message — see _NORMALIZED_MESSAGES

    @property
    def is_healthy(self) -> bool:
        return self.validation_status == ProviderValidationStatus.HEALTHY


def build_provider_config(
    pt: ProviderType, *, api_key: str | None, base_url: str | None
) -> ProviderConfig:
    """Build the ProviderConfig subclass for *pt*, carrying an INLINE secret
    reference over the already-decrypted key — never an env-var lookup, and
    the plaintext is never persisted anywhere by this function.

    Public (EP-23.3): shared by ``ProviderValidator`` (below, live credential
    validation) and ``app.services.provider_sync_service.ProviderSyncService``
    (usage synchronization) — the one place per-provider ``ProviderConfig``
    construction from a decrypted credential happens, so a new provider only
    ever needs one new ``match`` arm, not one per caller.
    """
    key_ref = (
        SecretReference(secret_store=SecretStoreType.INLINE, lookup_key=api_key)
        if api_key
        else None
    )
    match pt:
        case ProviderType.OPENAI:
            return OpenAIConfig(
                provider_type=pt.value,
                display_name="OpenAI",
                api_key_ref=key_ref,
                base_url=base_url,
            )
        case ProviderType.ANTHROPIC:
            return AnthropicConfig(
                provider_type=pt.value,
                display_name="Anthropic",
                api_key_ref=key_ref,
                base_url=base_url,
            )
        case ProviderType.GROK:
            return GrokConfig(
                provider_type=pt.value,
                display_name="Grok",
                api_key_ref=key_ref,
                base_url=base_url or "https://api.x.ai/v1",
            )
        case ProviderType.GOOGLE:
            return GoogleConfig(
                provider_type=pt.value,
                display_name="Google Gemini",
                api_key_ref=key_ref,
                base_url=base_url,
            )
        case ProviderType.AZURE_OPENAI:
            if not base_url:
                raise InvalidRequestError(
                    "Azure OpenAI requires a base_url (the resource endpoint).",
                    provider_type=pt.value,
                )
            return AzureOpenAIConfig(
                provider_type=pt.value,
                display_name="Azure OpenAI",
                api_key_ref=key_ref,
                azure_endpoint=base_url,
            )
        case ProviderType.OPENROUTER:
            return OpenRouterConfig(
                provider_type=pt.value,
                display_name="OpenRouter",
                api_key_ref=key_ref,
                base_url=base_url or "https://openrouter.ai/api/v1",
            )
        case ProviderType.OLLAMA:
            return OllamaConfig(
                provider_type=pt.value,
                display_name="Ollama",
                api_key_ref=key_ref,
                base_url=base_url or "http://localhost:11434",
            )
        case _:
            raise InvalidRequestError(
                f"No credential-validation support for provider {pt.value!r} yet.",
                provider_type=pt.value,
            )


class ProviderValidator:
    """Runs a live credential-validation probe and normalizes the result."""

    def __init__(self, registry: ProviderRegistry | None = None) -> None:
        self._factory = ProviderFactory(registry or get_registry())

    async def validate(
        self,
        pt: ProviderType,
        *,
        api_key: str | None,
        base_url: str | None = None,
    ) -> ValidationResult:
        """Validate *api_key* (already decrypted) against the live provider API."""
        try:
            config = build_provider_config(pt, api_key=api_key, base_url=base_url)
        except InvalidRequestError as exc:
            return self._result(ProviderValidationStatus.INVALID_API_KEY, detail=str(exc))

        adapter = self._factory.create(config)
        try:
            await adapter.verify_auth()
            return self._result(ProviderValidationStatus.HEALTHY)
        except InvalidRequestError:
            return self._result(ProviderValidationStatus.INVALID_API_KEY)
        except AuthenticationError as exc:
            status = (
                ProviderValidationStatus.UNAUTHORIZED
                if "forbidden" in str(exc).lower()
                else ProviderValidationStatus.INVALID_API_KEY
            )
            return self._result(status)
        except (RateLimitError, QuotaExceededError):
            return self._result(ProviderValidationStatus.QUOTA_EXCEEDED)
        except NetworkError as exc:
            status = (
                ProviderValidationStatus.TIMEOUT
                if "timed out" in str(exc).lower()
                else ProviderValidationStatus.NETWORK_FAILURE
            )
            return self._result(status)
        except (InternalProviderError, ProviderError, NotImplementedError):
            return self._result(ProviderValidationStatus.PROVIDER_UNAVAILABLE)
        finally:
            await adapter.aclose()

    @staticmethod
    def _result(status: ProviderValidationStatus, *, detail: str | None = None) -> ValidationResult:
        return ValidationResult(
            validation_status=status,
            health_status=_HEALTH_STATUS_FOR[status],
            detail=detail or _NORMALIZED_MESSAGES[status],
        )
