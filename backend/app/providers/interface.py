"""AIProvider abstract base class — F-024."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.provider_connection import ProviderType
from app.providers.capabilities import ProviderCapabilities
from app.providers.config import ProviderConfig
from app.providers.models import ConnectionStatus, ModelMetadata, ProviderRequest, ProviderResponse


class AIProvider(ABC):
    """Abstract base class for all AI provider adapters."""

    def __init__(self, config: ProviderConfig) -> None:
        self._config = config

    @property
    @abstractmethod
    def provider_type(self) -> ProviderType: ...

    @property
    @abstractmethod
    def capabilities(self) -> ProviderCapabilities: ...

    @abstractmethod
    async def check_connection(self) -> ConnectionStatus:
        """Test connectivity and return connection status. No side-effects."""
        ...

    @abstractmethod
    async def list_models(self) -> list[ModelMetadata]:
        """Return available models for this provider."""
        ...

    @abstractmethod
    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        """Submit a completion request. EP-07+ implements actual API calls."""
        ...

    @abstractmethod
    async def verify_auth(self) -> bool:
        """Verify that the configured credentials are valid."""
        ...

    @property
    def config(self) -> ProviderConfig:
        return self._config

    @property
    def display_name(self) -> str:
        return self._config.display_name
