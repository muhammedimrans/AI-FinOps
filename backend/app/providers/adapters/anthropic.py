"""Anthropic provider adapter stub — EP-06."""

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
        {"claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022", "claude-3-opus-20240229"}
    ),
)

_MODELS: list[ModelMetadata] = [
    ModelMetadata(
        id="claude-3-5-sonnet-20241022",
        display_name="Claude 3.5 Sonnet",
        provider_type="anthropic",
        context_window=200000,
        max_output_tokens=8192,
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
        id="claude-3-5-haiku-20241022",
        display_name="Claude 3.5 Haiku",
        provider_type="anthropic",
        context_window=200000,
        max_output_tokens=8192,
        capabilities=frozenset(
            {
                ModelCapabilityFlag.STREAMING,
                ModelCapabilityFlag.TOOL_CALLING,
                ModelCapabilityFlag.FUNCTION_CALLING,
            }
        ),
    ),
    ModelMetadata(
        id="claude-3-opus-20240229",
        display_name="Claude 3 Opus",
        provider_type="anthropic",
        context_window=200000,
        max_output_tokens=4096,
        capabilities=frozenset(
            {
                ModelCapabilityFlag.STREAMING,
                ModelCapabilityFlag.TOOL_CALLING,
                ModelCapabilityFlag.VISION,
                ModelCapabilityFlag.FUNCTION_CALLING,
            }
        ),
    ),
]


class AnthropicProvider(AIProvider):
    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.ANTHROPIC

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
        raise NotImplementedError("Anthropic completion is implemented in EP-07")

    async def verify_auth(self) -> bool:
        raise NotImplementedError("Anthropic auth verification is implemented in EP-07")
