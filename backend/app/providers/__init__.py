"""AI provider abstraction layer — EP-06."""

from __future__ import annotations

from app.providers.capabilities import ProviderCapabilities
from app.providers.errors import (
    AuthenticationError,
    InternalProviderError,
    InvalidRequestError,
    NetworkError,
    ProviderConfigurationError,
    ProviderError,
    QuotaExceededError,
    RateLimitError,
)
from app.providers.factory import ProviderFactory
from app.providers.interface import AIProvider
from app.providers.models import (
    AudioContent,
    ImageBase64Content,
    ImageUrlContent,
    Message,
    MessageContent,
    MessageRole,
    TextContent,
    ToolCall,
    ToolCallContent,
    ToolResultContent,
)
from app.providers.registry import ProviderRegistry

__all__ = [
    "AIProvider",
    "AudioContent",
    "AuthenticationError",
    "ImageBase64Content",
    "ImageUrlContent",
    "InternalProviderError",
    "InvalidRequestError",
    "Message",
    "MessageContent",
    "MessageRole",
    "NetworkError",
    "ProviderCapabilities",
    "ProviderConfigurationError",
    "ProviderError",
    "ProviderFactory",
    "ProviderRegistry",
    "QuotaExceededError",
    "RateLimitError",
    "TextContent",
    "ToolCall",
    "ToolCallContent",
    "ToolResultContent",
]
