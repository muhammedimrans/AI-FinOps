"""Grok (xAI) provider adapter stub — EP-06."""

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
    max_context_window=131072,
    supported_model_ids=frozenset({"grok-2-1212", "grok-2-vision-1212", "grok-beta"}),
)

_MODELS: list[ModelMetadata] = [
    ModelMetadata(
        id="grok-2-1212",
        display_name="Grok 2",
        provider_type="grok",
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
        id="grok-2-vision-1212",
        display_name="Grok 2 Vision",
        provider_type="grok",
        context_window=32768,
        capabilities=frozenset(
            {
                ModelCapabilityFlag.STREAMING,
                ModelCapabilityFlag.VISION,
                ModelCapabilityFlag.TOOL_CALLING,
                ModelCapabilityFlag.FUNCTION_CALLING,
            }
        ),
    ),
    ModelMetadata(
        id="grok-beta",
        display_name="Grok Beta",
        provider_type="grok",
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


class GrokProvider(AIProvider):
    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.GROK

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
        raise NotImplementedError("Grok completion is implemented in EP-07")

    async def verify_auth(self) -> bool:
        raise NotImplementedError("Grok auth verification is implemented in EP-07")
