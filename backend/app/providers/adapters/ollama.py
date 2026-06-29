"""Ollama provider adapter stub — EP-06."""

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
    supports_usage_api=False,
    has_rate_limits=False,
    requires_api_key=False,
    supports_oauth=False,
    supports_fine_tuning=False,
    supports_function_calling=True,
    max_context_window=None,
    supported_model_ids=frozenset(
        {"llama3.2", "llama3.1", "mistral", "codellama", "phi3", "gemma2"}
    ),
)

_MODELS: list[ModelMetadata] = [
    ModelMetadata(
        id="llama3.2",
        display_name="Llama 3.2",
        provider_type="ollama",
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
        id="llama3.1",
        display_name="Llama 3.1",
        provider_type="ollama",
        context_window=131072,
        capabilities=frozenset(
            {
                ModelCapabilityFlag.STREAMING,
                ModelCapabilityFlag.TOOL_CALLING,
                ModelCapabilityFlag.FUNCTION_CALLING,
            }
        ),
    ),
    ModelMetadata(
        id="mistral",
        display_name="Mistral",
        provider_type="ollama",
        context_window=32768,
        capabilities=frozenset(
            {
                ModelCapabilityFlag.STREAMING,
                ModelCapabilityFlag.TOOL_CALLING,
                ModelCapabilityFlag.FUNCTION_CALLING,
            }
        ),
    ),
    ModelMetadata(
        id="codellama",
        display_name="Code Llama",
        provider_type="ollama",
        context_window=16384,
        capabilities=frozenset({ModelCapabilityFlag.STREAMING}),
    ),
    ModelMetadata(
        id="phi3",
        display_name="Phi-3",
        provider_type="ollama",
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
        id="gemma2",
        display_name="Gemma 2",
        provider_type="ollama",
        context_window=8192,
        capabilities=frozenset({ModelCapabilityFlag.STREAMING}),
    ),
]


class OllamaProvider(AIProvider):
    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.OLLAMA

    @property
    def capabilities(self) -> ProviderCapabilities:
        return _CAPABILITIES

    async def check_connection(self) -> ConnectionStatus:
        return ConnectionStatus(
            is_connected=False,
            health_status=HealthStatus.UNKNOWN,
            checked_at=datetime.now(UTC),
        )

    async def list_models(self) -> list[ModelMetadata]:
        return list(_MODELS)

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        raise NotImplementedError("Ollama completion is implemented in EP-07")

    async def verify_auth(self) -> bool:
        raise NotImplementedError("Ollama auth verification is implemented in EP-07")

    async def check_capability(self, capability: str) -> bool:
        raise NotImplementedError("Ollama capability check is implemented in EP-07")

    @property
    def is_healthy(self) -> bool:
        return False

    async def get_usage(self, start_date: datetime, end_date: datetime) -> list[UsageData]:
        raise NotImplementedError("Ollama is self-hosted and does not expose a usage API")
