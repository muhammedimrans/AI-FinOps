"""
costorah.instrumentation — automatic AI provider usage capture.

    from costorah.instrumentation import OpenAIInstrumentor

    OpenAIInstrumentor().instrument()

    client = OpenAI()
    client.responses.create(model="gpt-4.1", input="Hello")

Every instrumentor implements the same `BaseInstrumentor` interface
(`instrument()`, `uninstrument()`, `is_instrumented()`, `extract_usage()`,
`normalize()`) — see `base.py`. Each provider's Python package is a lazy,
optional import: importing `costorah.instrumentation` itself never
requires any provider SDK to be installed; only calling a specific
instrumentor's `instrument()` does.
"""

from __future__ import annotations

from costorah.instrumentation._submission import set_default_client
from costorah.instrumentation.anthropic import AnthropicInstrumentor
from costorah.instrumentation.azure_openai import AzureOpenAIInstrumentor
from costorah.instrumentation.base import BaseInstrumentor, ExtractedUsage, InstrumentationError
from costorah.instrumentation.bedrock import BedrockInstrumentor
from costorah.instrumentation.cohere import CohereInstrumentor
from costorah.instrumentation.google import GeminiInstrumentor
from costorah.instrumentation.grok import GrokInstrumentor
from costorah.instrumentation.mistral import MistralInstrumentor
from costorah.instrumentation.ollama import OllamaInstrumentor
from costorah.instrumentation.openai import OpenAIInstrumentor
from costorah.instrumentation.openrouter import OpenRouterInstrumentor

__all__ = [
    "AnthropicInstrumentor",
    "AzureOpenAIInstrumentor",
    "BaseInstrumentor",
    "BedrockInstrumentor",
    "CohereInstrumentor",
    "ExtractedUsage",
    "GeminiInstrumentor",
    "GrokInstrumentor",
    "InstrumentationError",
    "MistralInstrumentor",
    "OllamaInstrumentor",
    "OpenAIInstrumentor",
    "OpenRouterInstrumentor",
    "set_default_client",
]
