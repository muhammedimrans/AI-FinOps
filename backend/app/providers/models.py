"""Common provider request/response models — F-032 / F-042 (EP-08)."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

# ── Model-level capability flags ──────────────────────────────────────────────


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


# ── Usage tracking ────────────────────────────────────────────────────────────


class UsageData(BaseModel):
    model_config = {"frozen": True}

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int | None = None


# ── EP-08: Normalized usage events ────────────────────────────────────────────


class NormalizedUsageEvent(BaseModel):
    """Provider-agnostic usage event produced by a UsageNormalizer (F-042).

    ``provider_request_id`` is the stable identifier used for deduplication —
    either the provider's own request ID or a deterministic hash derived from
    the aggregation key (date + model + org).
    """

    model_config = {"frozen": True}

    provider_request_id: str
    provider: str
    model: str
    timestamp: datetime
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int | None = None
    request_count: int = 1
    metadata: dict[str, Any] = Field(default_factory=dict)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class UsagePage(BaseModel):
    """One page of usage events returned by a provider adapter.

    ``next_cursor`` is an opaque string passed back on the next call to
    ``get_usage()`` to resume pagination.  ``has_more=False`` signals that
    the caller has received all events in the requested date range.
    """

    model_config = {"frozen": True}

    events: list[NormalizedUsageEvent] = Field(default_factory=list)
    next_cursor: str | None = None
    has_more: bool = False


# ── Health / connectivity ─────────────────────────────────────────────────────


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


# ── Message content types (REC-06) ────────────────────────────────────────────
# Discriminated union keyed on `type` — no ambiguity, fast Pydantic dispatch.


class TextContent(BaseModel):
    """Plain text content block."""

    model_config = {"frozen": True}
    type: Literal["text"] = "text"
    text: str


class ImageUrlContent(BaseModel):
    """Image referenced by a public or data-URI URL."""

    model_config = {"frozen": True}
    type: Literal["image_url"] = "image_url"
    url: str
    detail: str | None = None


class ImageBase64Content(BaseModel):
    """Inline base64-encoded image."""

    model_config = {"frozen": True}
    type: Literal["image_base64"] = "image_base64"
    data: str
    media_type: str = "image/jpeg"


class AudioContent(BaseModel):
    """Inline base64-encoded audio clip."""

    model_config = {"frozen": True}
    type: Literal["audio"] = "audio"
    data: str
    format: str = "wav"


class ToolCall(BaseModel):
    """A single tool invocation emitted by the model."""

    model_config = {"frozen": True}
    id: str
    name: str
    arguments: dict[str, Any]


class ToolCallContent(BaseModel):
    """Assistant turn that contains one or more tool calls."""

    model_config = {"frozen": True}
    type: Literal["tool_call"] = "tool_call"
    tool_calls: list[ToolCall]


class ToolResultContent(BaseModel):
    """Tool-result turn returned to the model after execution."""

    model_config = {"frozen": True}
    type: Literal["tool_result"] = "tool_result"
    tool_call_id: str
    content: str


MessageContent = Annotated[
    (
        TextContent
        | ImageUrlContent
        | ImageBase64Content
        | AudioContent
        | ToolCallContent
        | ToolResultContent
    ),
    Field(discriminator="type"),
]


# ── Message roles ─────────────────────────────────────────────────────────────


class MessageRole(enum.StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class Message(BaseModel):
    """Provider-neutral message in a conversation turn.

    `content` is either a plain string (simple text) or a list of typed content
    blocks (multimodal — vision, audio, tool calls).  Pydantic coerces plain
    dicts to this model automatically, so existing callers that pass
    ``{"role": "user", "content": "hello"}`` continue to work.
    """

    role: MessageRole
    content: str | list[MessageContent]
    name: str | None = None
    tool_call_id: str | None = None


# ── Request / response ────────────────────────────────────────────────────────


class ProviderRequest(BaseModel):
    model_id: str
    messages: list[Message]
    max_tokens: int | None = None
    temperature: float | None = None
    stream: bool = False
    extra: dict[str, Any] = Field(default_factory=dict)


class ProviderResponse(BaseModel):
    model_config = {"frozen": True}

    model_id: str
    content: str
    usage: UsageData | None = None
    finish_reason: str | None = None
    raw_response: dict[str, Any] = Field(default_factory=dict)
