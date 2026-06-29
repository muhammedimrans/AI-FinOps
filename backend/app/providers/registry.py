"""ProviderRegistry — F-025."""

from __future__ import annotations

from app.models.provider_connection import ProviderType
from app.providers.interface import AIProvider


class ProviderRegistry:
    """Central registry mapping ProviderType to AIProvider class."""

    def __init__(self) -> None:
        self._registry: dict[ProviderType, type[AIProvider]] = {}

    def register(self, provider_type: ProviderType, cls: type[AIProvider]) -> None:
        self._registry[provider_type] = cls

    def get(self, provider_type: ProviderType) -> type[AIProvider]:
        try:
            return self._registry[provider_type]
        except KeyError:
            raise KeyError(f"No provider registered for type {provider_type!r}") from None

    def is_registered(self, provider_type: ProviderType) -> bool:
        return provider_type in self._registry

    def registered_types(self) -> list[ProviderType]:
        return list(self._registry.keys())

    def __len__(self) -> int:
        return len(self._registry)


_default_registry: ProviderRegistry | None = None


def get_registry() -> ProviderRegistry:
    global _default_registry
    if _default_registry is None:
        from app.providers.factory import ProviderFactory

        _default_registry = ProviderFactory.build_default_registry()
    return _default_registry
