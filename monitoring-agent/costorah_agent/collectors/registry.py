"""
CollectorRegistry — maps provider/plugin names to BaseCollector classes.

Built-in collectors register themselves via `register_builtin_collectors()`.
Third-party plugins can register additional collectors the same way — the
registry has no built-in-vs-plugin distinction, which is the point: nothing
about the agent's core loop changes to support a new collector.
"""

from __future__ import annotations

from typing import Any

from costorah_agent.collectors.base import BaseCollector


class CollectorRegistry:
    """A name -> BaseCollector-subclass mapping, with instantiation helpers."""

    def __init__(self) -> None:
        self._collectors: dict[str, type[BaseCollector]] = {}

    def register(self, name: str, collector_cls: type[BaseCollector]) -> None:
        if not issubclass(collector_cls, BaseCollector):
            raise TypeError(f"{collector_cls!r} must subclass BaseCollector")
        self._collectors[name] = collector_cls

    def unregister(self, name: str) -> None:
        self._collectors.pop(name, None)

    def is_registered(self, name: str) -> bool:
        return name in self._collectors

    def registered_names(self) -> list[str]:
        return sorted(self._collectors)

    def build(self, name: str, config: dict[str, Any]) -> BaseCollector:
        try:
            collector_cls = self._collectors[name]
        except KeyError as exc:
            raise KeyError(
                f"No collector registered for {name!r}. Registered: {self.registered_names()}"
            ) from exc
        return collector_cls(config)

    def build_enabled(
        self, enabled_names: list[str], config_by_provider: dict[str, dict[str, Any]]
    ) -> dict[str, BaseCollector]:
        """
        Build every collector named in `enabled_names` that has a registered
        implementation. Unrecognized names are skipped (not raised) — a
        provider listed as enabled in config.yaml with no implementation
        yet (e.g. grok, cohere, bedrock, mistral as of EP-17) is a
        forward-compatibility no-op, not a startup failure.
        """
        built: dict[str, BaseCollector] = {}
        for name in enabled_names:
            if not self.is_registered(name):
                continue
            built[name] = self.build(name, config_by_provider.get(name, {}))
        return built


def register_builtin_collectors(registry: CollectorRegistry) -> None:
    """Register every collector shipped with the agent itself."""
    from costorah_agent.collectors.anthropic import AnthropicCollector
    from costorah_agent.collectors.azure_openai import AzureOpenAICollector
    from costorah_agent.collectors.google import GoogleCollector
    from costorah_agent.collectors.ollama import OllamaCollector
    from costorah_agent.collectors.openai import OpenAICollector
    from costorah_agent.collectors.openrouter import OpenRouterCollector

    registry.register("openai", OpenAICollector)
    registry.register("anthropic", AnthropicCollector)
    registry.register("google", GoogleCollector)
    registry.register("azure", AzureOpenAICollector)
    registry.register("openrouter", OpenRouterCollector)
    registry.register("ollama", OllamaCollector)


_default_registry: CollectorRegistry | None = None


def get_default_registry() -> CollectorRegistry:
    """Return a process-wide singleton registry with builtins registered."""
    global _default_registry
    if _default_registry is None:
        _default_registry = CollectorRegistry()
        register_builtin_collectors(_default_registry)
    return _default_registry
