"""ProviderFactory — F-026."""

from __future__ import annotations

from app.models.provider_connection import ProviderType
from app.providers.config import ProviderConfig
from app.providers.errors import ProviderConfigurationError
from app.providers.interface import AIProvider
from app.providers.registry import ProviderRegistry


class ProviderFactory:
    """Instantiate provider adapters from config, with credential injection."""

    def __init__(self, registry: ProviderRegistry) -> None:
        self._registry = registry

    def create(self, config: ProviderConfig) -> AIProvider:
        """Construct the adapter registered for ``config.provider_type``.

        Post-construction validation (REC-03)
        --------------------------------------
        After instantiation we verify that the adapter's own ``provider_type``
        property matches the registry key used to look it up.  A mismatch
        indicates a registry misconfiguration (e.g. ``AnthropicProvider``
        accidentally registered under ``ProviderType.OPENAI``) and would
        otherwise cause silent wrong-provider execution.
        """
        provider_type = ProviderType(config.provider_type)
        cls = self._registry.get(provider_type)
        instance = cls(config)

        if instance.provider_type != provider_type:
            raise ProviderConfigurationError(
                f"Registry misconfiguration: {cls.__name__} is registered under "
                f"{provider_type!r} but its provider_type property reports "
                f"{instance.provider_type!r}. Fix ProviderFactory.build_default_registry().",
                provider_type=config.provider_type,
            )

        return instance

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
