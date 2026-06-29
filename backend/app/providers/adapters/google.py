"""Google provider adapter stub — EP-06."""

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
    supports_audio=True,
    supports_usage_api=True,
    has_rate_limits=True,
    requires_api_key=True,
    supports_oauth=True,
    supports_fine_tuning=True,
    supports_function_calling=True,
    max_context_window=2000000,
    supported_model_ids=frozenset(
        {"gemini-1.5-pro", "gemini-1.5-flash", "gemini-1.5-flash-8b", "gemini-2.0-flash"}
    ),
)

_MODELS: list[ModelMetadata] = [
    ModelMetadata(
        id="gemini-1.5-pro",
        display_name="Gemini 1.5 Pro",
        provider_type="google",
        context_window=2000000,
        max_output_tokens=8192,
        capabilities=frozenset(
            {
                ModelCapabilityFlag.STREAMING,
                ModelCapabilityFlag.TOOL_CALLING,
                ModelCapabilityFlag.VISION,
                ModelCapabilityFlag.AUDIO,
                ModelCapabilityFlag.FUNCTION_CALLING,
            }
        ),
    ),
    ModelMetadata(
        id="gemini-1.5-flash",
        display_name="Gemini 1.5 Flash",
        provider_type="google",
        context_window=1000000,
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
        id="gemini-1.5-flash-8b",
        display_name="Gemini 1.5 Flash 8B",
        provider_type="google",
        context_window=1000000,
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
        id="gemini-2.0-flash",
        display_name="Gemini 2.0 Flash",
        provider_type="google",
        context_window=1000000,
        max_output_tokens=8192,
        capabilities=frozenset(
            {
                ModelCapabilityFlag.STREAMING,
                ModelCapabilityFlag.TOOL_CALLING,
                ModelCapabilityFlag.VISION,
                ModelCapabilityFlag.AUDIO,
                ModelCapabilityFlag.FUNCTION_CALLING,
            }
        ),
    ),
]


class GoogleProvider(AIProvider):
    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.GOOGLE

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
        raise NotImplementedError("Google completion is implemented in EP-07")

    async def verify_auth(self) -> bool:
        raise NotImplementedError("Google auth verification is implemented in EP-07")
