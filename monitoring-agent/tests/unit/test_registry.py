from __future__ import annotations

import pytest

from costorah_agent.collectors.base import BaseCollector
from costorah_agent.collectors.models import CollectorHealth, NormalizedUsageEvent
from costorah_agent.collectors.registry import CollectorRegistry, get_default_registry


class _DummyCollector(BaseCollector):
    name = "dummy"

    async def collect(self) -> list[NormalizedUsageEvent]:
        return []

    def normalize(self, raw: object) -> NormalizedUsageEvent:
        raise NotImplementedError

    async def health(self) -> CollectorHealth:
        return CollectorHealth(name=self.name, enabled=True, healthy=True, detail="ok")


def test_register_and_build() -> None:
    registry = CollectorRegistry()
    registry.register("dummy", _DummyCollector)
    collector = registry.build("dummy", {"foo": "bar"})
    assert isinstance(collector, _DummyCollector)
    assert collector.config == {"foo": "bar"}


def test_register_rejects_non_collector_subclass() -> None:
    registry = CollectorRegistry()
    with pytest.raises(TypeError):
        registry.register("bad", object)  # type: ignore[arg-type]


def test_build_unregistered_name_raises_key_error() -> None:
    registry = CollectorRegistry()
    with pytest.raises(KeyError):
        registry.build("nonexistent", {})


def test_is_registered_and_unregister() -> None:
    registry = CollectorRegistry()
    registry.register("dummy", _DummyCollector)
    assert registry.is_registered("dummy") is True
    registry.unregister("dummy")
    assert registry.is_registered("dummy") is False


def test_registered_names_sorted() -> None:
    registry = CollectorRegistry()
    registry.register("zeta", _DummyCollector)
    registry.register("alpha", _DummyCollector)
    assert registry.registered_names() == ["alpha", "zeta"]


def test_build_enabled_skips_unregistered_names() -> None:
    registry = CollectorRegistry()
    registry.register("dummy", _DummyCollector)
    built = registry.build_enabled(["dummy", "grok", "cohere"], {})
    assert list(built) == ["dummy"]


def test_build_enabled_passes_per_provider_config() -> None:
    registry = CollectorRegistry()
    registry.register("dummy", _DummyCollector)
    built = registry.build_enabled(["dummy"], {"dummy": {"api_key": "x"}})
    assert built["dummy"].config == {"api_key": "x"}


def test_default_registry_has_all_six_builtin_collectors() -> None:
    registry = get_default_registry()
    assert set(registry.registered_names()) == {
        "anthropic",
        "azure",
        "google",
        "ollama",
        "openai",
        "openrouter",
    }
