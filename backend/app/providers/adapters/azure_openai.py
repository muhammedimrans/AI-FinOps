"""Azure OpenAI provider adapter stub — EP-06."""

from __future__ import annotations

from datetime import UTC, datetime

from app.models.provider_connection import ProviderType
from app.providers.capabilities import ProviderCapabilities
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
    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.AZURE_OPENAI

    @property
    def capabilities(self) -> ProviderCapabilities:
        return _CAPABILITIES

    async def check_connection(self) -> ConnectionStatus:
        return ConnectionStatus(
            is_connected=False,
            health_status=HealthStatus.UNKNOWN,
            checked_at=datetime.now(UTC),
        )

    async def verify_auth(self) -> bool:
        raise NotImplementedError("Azure OpenAI auth verification is implemented in EP-07")

    async def check_capability(self, capability: str) -> bool:
        raise NotImplementedError("Azure OpenAI capability check is implemented in EP-07")

    @property
    def is_healthy(self) -> bool:
        return False

    async def list_models(self) -> list[ModelMetadata]:
        return list(_MODELS)

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        raise NotImplementedError("Azure OpenAI completion is implemented in EP-07")

    async def get_usage(self, start_date: datetime, end_date: datetime) -> list[UsageData]:
        raise NotImplementedError("Azure OpenAI usage fetching is implemented in EP-08")
