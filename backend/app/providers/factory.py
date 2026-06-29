"""ProviderFactory — F-026."""

from __future__ import annotations

from app.models.provider_connection import ProviderType
from app.providers.config import ProviderConfig
from app.providers.interface import AIProvider
from app.providers.registry import ProviderRegistry


class ProviderFactory:
    """Instantiate provider adapters from config, with credential injection."""

    def __init__(self, registry: ProviderRegistry) -> None:
        self._registry = registry

    def create(self, config: ProviderConfig) -> AIProvider:
        provider_type = ProviderType(config.provider_type)
        cls = self._registry.get(provider_type)
        return cls(config)

    @staticmethod
    def build_default_registry() -> ProviderRegistry:
        """Build and return a registry with all built-in adapter stubs registered."""
        from app.providers.adapters.anthropic import AnthropicProvider
        from app.providers.adapters.azure_openai import AzureOpenAIProvider
        from app.providers.adapters.google import GoogleProvider
        from app.providers.adapters.grok import GrokProvider
        from app.providers.adapters.ollama import OllamaProvider
        from app.providers.adapters.openai import OpenAIProvider
        from app.providers.adapters.openrouter import OpenRouterProvider

        registry = ProviderRegistry()
        registry.register(ProviderType.OPENAI, OpenAIProvider)
        registry.register(ProviderType.ANTHROPIC, AnthropicProvider)
        registry.register(ProviderType.GROK, GrokProvider)
        registry.register(ProviderType.GOOGLE, GoogleProvider)
        registry.register(ProviderType.AZURE_OPENAI, AzureOpenAIProvider)
        registry.register(ProviderType.OPENROUTER, OpenRouterProvider)
        registry.register(ProviderType.OLLAMA, OllamaProvider)
        return registry
