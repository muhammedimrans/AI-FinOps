"""ProviderCapabilities dataclass — F-027."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
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
    supported_model_ids: frozenset[str] = field(default_factory=frozenset)
