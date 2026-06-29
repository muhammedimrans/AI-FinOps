"""ProviderInfo response model — F-040.

Flattens ProviderCapabilities fields directly so Pydantic serialises cleanly
without nesting a frozen dataclass inside a BaseModel (which causes schema
generation issues in Pydantic v2).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.providers.capabilities import ProviderCapabilities
from app.providers.models import HealthStatus


class ProviderInfo(BaseModel):
    """Serialisable snapshot of a provider's identity, capabilities, and health."""

    model_config = {"frozen": True}

    # Identity
    provider: str
    display_name: str
    version: str = "1.0.0"
    api_version: str | None = None
    authentication_type: str = "api_key"
    documentation_url: str | None = None

    # Health
    health: HealthStatus = HealthStatus.UNKNOWN

    # Capability flags (flattened from ProviderCapabilities)
    supports_streaming: bool = False
    supports_tool_calling: bool = False
    supports_vision: bool = False
    supports_audio: bool = False
    supports_usage_api: bool = False
    has_rate_limits: bool = True
    requires_api_key: bool = True
    supports_oauth: bool = False
    supports_fine_tuning: bool = False
    supports_function_calling: bool = False
    supports_web_sessions: bool = False
    max_context_window: int | None = None
    supported_model_ids: list[str] = Field(default_factory=list)

    @classmethod
    def from_capabilities(
        cls,
        *,
        provider: str,
        display_name: str,
        capabilities: ProviderCapabilities,
        health: HealthStatus = HealthStatus.UNKNOWN,
        version: str = "1.0.0",
        api_version: str | None = None,
        authentication_type: str = "api_key",
        documentation_url: str | None = None,
    ) -> ProviderInfo:
        return cls(
            provider=provider,
            display_name=display_name,
            version=version,
            api_version=api_version,
            authentication_type=authentication_type,
            documentation_url=documentation_url,
            health=health,
            supports_streaming=capabilities.supports_streaming,
            supports_tool_calling=capabilities.supports_tool_calling,
            supports_vision=capabilities.supports_vision,
            supports_audio=capabilities.supports_audio,
            supports_usage_api=capabilities.supports_usage_api,
            has_rate_limits=capabilities.has_rate_limits,
            requires_api_key=capabilities.requires_api_key,
            supports_oauth=capabilities.supports_oauth,
            supports_fine_tuning=capabilities.supports_fine_tuning,
            supports_function_calling=capabilities.supports_function_calling,
            supports_web_sessions=capabilities.supports_web_sessions,
            max_context_window=capabilities.max_context_window,
            supported_model_ids=sorted(capabilities.supported_model_ids),
        )
