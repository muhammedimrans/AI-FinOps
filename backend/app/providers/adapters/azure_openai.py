"""Azure OpenAI provider adapter — EP-22 (validation), EP-06 (catalog/capabilities).

Authentication
--------------
``api-key: <api_key>`` header against the customer's own Azure resource
endpoint (``AzureOpenAIConfig.azure_endpoint`` — there is no shared
``api.x.com``-style base URL; every Azure OpenAI customer has a distinct
per-resource hostname).

Live API calls
---------------
``GET {azure_endpoint}/openai/deployments?api-version=<api_version>`` —
"deployment validation" per the EP-22 spec: Azure OpenAI has no bare model
list, only a list of the customer's configured deployments, which is the
correct live signal that both the key and the endpoint are valid.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import httpx

from app.http.auth import ApiKeyHeaderAuth
from app.http.client import ProviderHttpClient
from app.http.transport import HttpxTransport
from app.models.provider_connection import ProviderType
from app.providers.capabilities import ProviderCapabilities
from app.providers.config import AzureOpenAIConfig, ProviderConfig
from app.providers.credential import CredentialValidator, SecretResolver
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

if TYPE_CHECKING:
    from app.providers.info import ProviderInfo
    from app.providers.models import UsagePage

_DEFAULT_API_VERSION = "2024-02-01"

_CAPABILITIES = ProviderCapabilities(
    supports_streaming=True,
    supports_tool_calling=True,
    supports_vision=True,
    supports_audio=False,
    supports_usage_api=True,
    has_rate_limits=True,
    requires_api_key=True,
    supports_oauth=True,
    supports_fine_tuning=True,
    supports_function_calling=True,
    max_context_window=128000,
    supported_model_ids=frozenset({"gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-35-turbo"}),
)

_MODELS: list[ModelMetadata] = [
    ModelMetadata(
        id="gpt-4o",
        display_name="GPT-4o (Azure)",
        provider_type="azure_openai",
        context_window=128000,
        capabilities=frozenset(
            {
                ModelCapabilityFlag.STREAMING,
                ModelCapabilityFlag.TOOL_CALLING,
                ModelCapabilityFlag.VISION,
                ModelCapabilityFlag.FUNCTION_CALLING,
            }
        ),
    ),
    ModelMetadata(
        id="gpt-4o-mini",
        display_name="GPT-4o Mini (Azure)",
        provider_type="azure_openai",
        context_window=128000,
        capabilities=frozenset(
            {
                ModelCapabilityFlag.STREAMING,
                ModelCapabilityFlag.TOOL_CALLING,
                ModelCapabilityFlag.VISION,
                ModelCapabilityFlag.FUNCTION_CALLING,
            }
        ),
    ),
    ModelMetadata(
        id="gpt-4-turbo",
        display_name="GPT-4 Turbo (Azure)",
        provider_type="azure_openai",
        context_window=128000,
        capabilities=frozenset(
            {
                ModelCapabilityFlag.STREAMING,
                ModelCapabilityFlag.TOOL_CALLING,
                ModelCapabilityFlag.FUNCTION_CALLING,
            }
        ),
    ),
    ModelMetadata(
        id="gpt-35-turbo",
        display_name="GPT-3.5 Turbo (Azure)",
        provider_type="azure_openai",
        context_window=16385,
        capabilities=frozenset({ModelCapabilityFlag.STREAMING}),
        is_deprecated=True,
    ),
]


class AzureOpenAIProvider(AIProvider):
    """Azure OpenAI provider adapter (EP-22)."""

    def __init__(
        self,
        config: ProviderConfig,
        *,
        http_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(config)
        self._healthy: bool = False
        self._last_checked: datetime | None = None
        self._transport = HttpxTransport(
            base_url=self._endpoint(),
            verify=True,
            mock_transport=http_transport,
        )

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.AZURE_OPENAI

    @property
    def capabilities(self) -> ProviderCapabilities:
        return _CAPABILITIES

    @property
    def is_healthy(self) -> bool:
        return self._healthy

    def _endpoint(self) -> str:
        if isinstance(self._config, AzureOpenAIConfig) and self._config.azure_endpoint:
            return self._config.azure_endpoint
        from app.providers.errors import AuthenticationError

        raise AuthenticationError(
            "Azure OpenAI provider has no azure_endpoint configured",
            provider_type="azure_openai",
        )

    def _api_version(self) -> str:
        if isinstance(self._config, AzureOpenAIConfig):
            return self._config.api_version
        return _DEFAULT_API_VERSION

    def _build_client(self, api_key: str) -> ProviderHttpClient:
        return ProviderHttpClient(
            base_url=self._endpoint(),
            auth=ApiKeyHeaderAuth("api-key", api_key),
            provider_type="azure_openai",
            timeout=self._config.timeout_seconds,
            transport=self._transport,
        )

    def _resolve_key(self) -> str:
        if self._config.api_key_ref is None:
            from app.providers.errors import AuthenticationError

            raise AuthenticationError(
                "Azure OpenAI provider has no api_key_ref configured",
                provider_type="azure_openai",
            )
        return SecretResolver.resolve(self._config.api_key_ref, provider_type="azure_openai")

    async def verify_auth(self) -> bool:
        """Live GET .../openai/deployments — "deployment validation" per the EP-22 spec."""
        key = self._resolve_key()
        CredentialValidator.validate_azure_key(key)
        async with self._build_client(key) as client:
            await client.get("/openai/deployments", params={"api-version": self._api_version()})
        return True

    async def check_connection(self) -> ConnectionStatus:
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
        return list(_MODELS)

    async def aclose(self) -> None:
        await self._transport.aclose()

    async def __aenter__(self) -> AzureOpenAIProvider:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        """Submit a chat completion request — EP-25.4 (AI Playground).

        POST {endpoint}/openai/deployments/{deployment}/chat/completions —
        ``request.model_id`` is the deployment name (Azure has no bare
        model-id completion endpoint, only per-deployment ones, matching
        ``verify_auth()``'s own "deployment validation" convention above).
        """
        key = self._resolve_key()
        payload: dict[str, Any] = {
            "messages": [{"role": m.role.value, "content": m.content} for m in request.messages],
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        payload.update(request.extra)

        async with self._build_client(key) as client:
            data = await client.post(
                f"/openai/deployments/{request.model_id}/chat/completions",
                json=payload,
                params={"api-version": self._api_version()},
            )

        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        usage = data.get("usage") or {}
        return ProviderResponse(
            model_id=data.get("model", request.model_id),
            content=message.get("content") or "",
            usage=UsageData(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            ),
            finish_reason=choice.get("finish_reason"),
            raw_response=data,
        )

    async def get_usage(
        self,
        start_date: datetime,
        end_date: datetime,
        *,
        cursor: str | None = None,
        limit: int = 100,
    ) -> UsagePage:
        """No bulk usage-history endpoint exists for an Azure OpenAI resource
        key. Cost/usage data for an Azure resource lives in Azure Cost
        Management (an ARM/subscription-level API requiring a service
        principal or management-plane credential), not the data-plane
        ``api-key`` this connection stores for inference calls — there is no
        usage call this adapter's credential is authorized to make. An
        honest empty page (not fabricated events) is returned; see
        CLAUDE.md's EP-24.3 section for the full per-provider accounting.
        The sync pipeline itself (checkpoint, retry, scheduler) still runs
        normally — this is the correct, honest 0-record outcome, not a
        skipped/unsupported provider.
        """
        from app.providers.models import UsagePage

        return UsagePage()

    def get_provider_info(self, health: HealthStatus | None = None) -> ProviderInfo:
        from app.providers.info import ProviderInfo

        return ProviderInfo.from_capabilities(
            provider=self.provider_type.value,
            display_name=self._config.display_name,
            capabilities=_CAPABILITIES,
            health=health if health is not None else HealthStatus.UNKNOWN,
        )
