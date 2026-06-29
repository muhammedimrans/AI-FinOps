"""Common provider request/response models — F-032."""

from __future__ import annotations

import enum
from datetime import datetime

from pydantic import BaseModel, Field


class ModelCapabilityFlag(enum.StrEnum):
    STREAMING = "streaming"
    TOOL_CALLING = "tool_calling"
    VISION = "vision"
    AUDIO = "audio"
    FUNCTION_CALLING = "function_calling"
    FINE_TUNING = "fine_tuning"


class ModelMetadata(BaseModel):
    model_config = {"frozen": True}

    id: str
    display_name: str
    provider_type: str
    context_window: int | None = None
    max_output_tokens: int | None = None
    capabilities: frozenset[ModelCapabilityFlag] = Field(default_factory=frozenset)
    input_cost_per_1k: float | None = None
    output_cost_per_1k: float | None = None
    is_deprecated: bool = False
    deprecated_at: datetime | None = None


class UsageData(BaseModel):
    model_config = {"frozen": True}

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int | None = None


class HealthStatus(enum.StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class ConnectionStatus(BaseModel):
    model_config = {"frozen": True}

    is_connected: bool
    health_status: HealthStatus
    latency_ms: float | None = None
    error_message: str | None = None
    checked_at: datetime


class ProviderRequest(BaseModel):
    model_id: str
    messages: list[dict[str, str]]
    max_tokens: int | None = None
    temperature: float | None = None
    stream: bool = False
    extra: dict = Field(default_factory=dict)


class ProviderResponse(BaseModel):
    model_config = {"frozen": True}

    model_id: str
    content: str
    usage: UsageData | None = None
    finish_reason: str | None = None
    raw_response: dict = Field(default_factory=dict)
