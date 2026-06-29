"""Anthropic provider adapter — F-035 (EP-07).

Implements verify_auth, check_connection, is_healthy, list_models,
check_capability, and get_provider_info.  Completion and usage are
deferred to EP-07+ and EP-08 respectively.

Authentication
--------------
x-api-key: <api_key>
anthropic-version: 2023-06-01

Live API calls
--------------
GET /v1/models — model discovery (requires valid key; beta feature)
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

import httpx

from app.http.auth import ApiKeyHeaderAuth, CompositeAuth
from app.http.client import ProviderHttpClient
from app.models.provider_connection import ProviderType
from app.providers.capabilities import ProviderCapabilities
from app.providers.config import ProviderConfig
from app.providers.credential import CredentialValidator, SecretResolver
from app.providers.info import ProviderInfo
from app.providers.interface import AIProvider
from app.providers.models import (
    ConnectionStatus,
    HealthStatus,
    ModelCapabilityFlag,
    ModelMetadata,
    ProviderRequest,
    ProviderResponse,
    UsageData,
)

_BASE_URL = "https://api.anthropic.com"
_API_VERSION = "2023-06-01"
_DOCS_URL = "https://docs.anthropic.com"

_CAPABILITIES = ProviderCapabilities(
    supports_streaming=True,
    supports_tool_calling=True,
    supports_vision=True,
    supports_audio=False,
    supports_usage_api=True,
    has_rate_limits=True,
    requires_api_key=True,
    supports_oauth=False,
    supports_fine_tuning=False,
    supports_function_calling=True,
    max_context_window=200000,
    supported_model_ids=frozenset(
        {"claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022", "claude-3-opus-20240229"}
    ),
)

# Static enrichment for well-known Claude models.
_MODEL_ENRICHMENT: dict[str, dict[str, Any]] = {
    "claude-3-5-sonnet-20241022": {
        "display_name": "Claude 3.5 Sonnet",
        "context_window": 200000,
        "max_output_tokens": 8192,
        "capabilities": frozenset(
            {
                ModelCapabilityFlag.STREAMING,
                ModelCapabilityFlag.TOOL_CALLING,
                ModelCapabilityFlag.VISION,
                ModelCapabilityFlag.FUNCTION_CALLING,
            }
        ),
    },
    "claude-3-5-haiku-20241022": {
        "display_name": "Claude 3.5 Haiku",
        "context_window": 200000,
        "max_output_tokens": 8192,
        "capabilities": frozenset(
            {
                ModelCapabilityFlag.STREAMING,
                ModelCapabilityFlag.TOOL_CALLING,
                ModelCapabilityFlag.FUNCTION_CALLING,
            }
        ),
    },
    "claude-3-opus-20240229": {
        "display_name": "Claude 3 Opus",
        "context_window": 200000,
        "max_output_tokens": 4096,
        "capabilities": frozenset(
            {
                ModelCapabilityFlag.STREAMING,
                ModelCapabilityFlag.TOOL_CALLING,
                ModelCapabilityFlag.VISION,
                ModelCapabilityFlag.FUNCTION_CALLING,
            }
        ),
    },
}


def _enrich_model(model_id: str) -> ModelMetadata:
    enrichment = _MODEL_ENRICHMENT.get(model_id, {})
    return ModelMetadata(
        id=model_id,
        display_name=enrichment.get("display_name", model_id),
        provider_type="anthropic",
        context_window=enrichment.get("context_window"),
        max_output_tokens=enrichment.get("max_output_tokens"),
        capabilities=enrichment.get("capabilities", frozenset()),
        is_deprecated=enrichment.get("is_deprecated", False),
    )


class AnthropicProvider(AIProvider):
    """Production Anthropic provider adapter (EP-07)."""

    def __init__(
        self,
        config: ProviderConfig,
        *,
        http_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(config)
        self._http_transport = http_transport
        self._healthy: bool = False
        self._last_checked: datetime | None = None

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.ANTHROPIC

    @property
    def capabilities(self) -> ProviderCapabilities:
        return _CAPABILITIES

    @property
    def is_healthy(self) -> bool:
        return self._healthy

    def _get_api_version(self) -> str:
        from app.providers.config import AnthropicConfig

        if isinstance(self._config, AnthropicConfig):
            return self._config.anthropic_version
        return _API_VERSION

    def _build_client(self, api_key: str) -> ProviderHttpClient:
        auth = CompositeAuth(
            ApiKeyHeaderAuth("x-api-key", api_key),
            ApiKeyHeaderAuth("anthropic-version", self._get_api_version()),
        )
        return ProviderHttpClient(
            base_url=self._config.base_url or _BASE_URL,
            auth=auth,
            provider_type="anthropic",
            timeout=self._config.timeout_seconds,
            mock_transport=self._http_transport,
        )

    def _resolve_key(self) -> str:
        if self._config.api_key_ref is None:
            from app.providers.errors import AuthenticationError

            raise AuthenticationError(
                "Anthropic provider has no api_key_ref configured",
                provider_type="anthropic",
            )
        return SecretResolver.resolve(self._config.api_key_ref, provider_type="anthropic")

    async def verify_auth(self) -> bool:
        """Make a live API call to confirm the key is valid.

        Uses GET /v1/models — requires a valid key.
        Returns True on success, raises AuthenticationError on 401/403.
        """
        key = self._resolve_key()
        CredentialValidator.validate_anthropic_key(key)
        async with self._build_client(key) as client:
            await client.get("/v1/models")
        return True

    async def check_connection(self) -> ConnectionStatus:
        """Probe the Anthropic API and cache the health state."""
        start = time.monotonic()
        try:
            await self.verify_auth()
            latency = round((time.monotonic() - start) * 1000, 2)
            self._healthy = True
            self._last_checked = datetime.now(UTC)
            return ConnectionStatus(
                is_connected=True,
                health_status=HealthStatus.HEALTHY,
                latency_ms=latency,
                checked_at=self._last_checked,
            )
        except Exception as exc:
            latency = round((time.monotonic() - start) * 1000, 2)
            self._healthy = False
            self._last_checked = datetime.now(UTC)
            return ConnectionStatus(
                is_connected=False,
                health_status=HealthStatus.UNHEALTHY,
                latency_ms=latency,
                error_message=str(exc),
                checked_at=self._last_checked,
            )

    async def check_capability(self, capability: str) -> bool:
        cap = capability.lower()
        return getattr(_CAPABILITIES, f"supports_{cap}", False) or getattr(
            _CAPABILITIES, cap, False
        )

    async def list_models(self) -> list[ModelMetadata]:
        """Fetch live model list from the API and enrich with static metadata."""
        key = self._resolve_key()
        CredentialValidator.validate_anthropic_key(key)
        async with self._build_client(key) as client:
            data = await client.get("/v1/models")
        raw_models: list[dict[str, Any]] = data.get("data", [])
        return [_enrich_model(m["id"]) for m in raw_models if "id" in m]

    def get_provider_info(self, health: HealthStatus | None = None) -> ProviderInfo:
        return ProviderInfo.from_capabilities(
            provider="anthropic",
            display_name=self._config.display_name,
            capabilities=_CAPABILITIES,
            health=(
                health
                if health is not None
                else (HealthStatus.HEALTHY if self._healthy else HealthStatus.UNKNOWN)
            ),
            api_version=self._get_api_version(),
            documentation_url=_DOCS_URL,
        )

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        raise NotImplementedError("Anthropic completion is implemented in a later EP")

    async def get_usage(self, start_date: datetime, end_date: datetime) -> list[UsageData]:
        raise NotImplementedError("Anthropic usage fetching is implemented in EP-08")
