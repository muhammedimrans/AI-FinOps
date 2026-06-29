"""OpenRouter provider adapter stub — EP-06."""

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
)

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
        {
            "openai/gpt-4o",
            "anthropic/claude-3-5-sonnet",
            "google/gemini-pro-1.5",
            "meta-llama/llama-3.1-405b-instruct",
        }
    ),
)

_MODELS: list[ModelMetadata] = [
    ModelMetadata(
        id="openai/gpt-4o",
        display_name="GPT-4o (via OpenRouter)",
        provider_type="openrouter",
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
        id="anthropic/claude-3-5-sonnet",
        display_name="Claude 3.5 Sonnet (via OpenRouter)",
        provider_type="openrouter",
        context_window=200000,
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
        id="google/gemini-pro-1.5",
        display_name="Gemini 1.5 Pro (via OpenRouter)",
        provider_type="openrouter",
        context_window=2000000,
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
        id="meta-llama/llama-3.1-405b-instruct",
        display_name="Llama 3.1 405B (via OpenRouter)",
        provider_type="openrouter",
        context_window=131072,
        capabilities=frozenset(
            {
                ModelCapabilityFlag.STREAMING,
                ModelCapabilityFlag.TOOL_CALLING,
                ModelCapabilityFlag.FUNCTION_CALLING,
            }
        ),
    ),
]


class OpenRouterProvider(AIProvider):
    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.OPENROUTER

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
        raise NotImplementedError("OpenRouter completion is implemented in EP-07")

    async def verify_auth(self) -> bool:
        raise NotImplementedError("OpenRouter auth verification is implemented in EP-07")
