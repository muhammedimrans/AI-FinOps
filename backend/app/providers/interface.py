"""AIProvider abstract base class — F-024."""

from __future__ import annotations

from abc import abstractmethod
from datetime import datetime

from app.models.provider_connection import ProviderType
from app.providers.capabilities import ProviderCapabilities
from app.providers.config import ProviderConfig
from app.providers.health import HealthCheckInterface
from app.providers.info import ProviderInfo
from app.providers.models import (
    HealthStatus,
    ModelMetadata,
    ProviderRequest,
    ProviderResponse,
    UsagePage,
)


class AIProvider(HealthCheckInterface):
    """Abstract base class for all AI provider adapters.

    Design note (EP-06.5 / REC-01)
    --------------------------------
    ``AIProvider`` now inherits from ``HealthCheckInterface`` rather than
    duplicating its method signatures.  This eliminates the orphaned ABC and
    makes the health contract explicit: every adapter that implements
    ``AIProvider`` automatically satisfies ``HealthCheckInterface``, so a
    generic health-dashboard component can depend on the smaller interface
    without taking a dependency on the full adapter.

    ``check_connection`` and ``verify_auth`` are inherited as abstract methods
    from ``HealthCheckInterface``.  ``check_capability`` and ``is_healthy`` are
    also inherited; adapters must implement them.
    """

    def __init__(self, config: ProviderConfig) -> None:
        self._config = config

    # ── Identity ──────────────────────────────────────────────────────────────

    @property
    @abstractmethod
    def provider_type(self) -> ProviderType: ...

    @property
    @abstractmethod
    def capabilities(self) -> ProviderCapabilities: ...

    # ── Core operations ───────────────────────────────────────────────────────

    @abstractmethod
    async def list_models(self) -> list[ModelMetadata]:
        """Return available models for this provider."""
        ...

    @abstractmethod
    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        """Submit a completion request. EP-07+ implements actual API calls."""
        ...

    # ── Usage (EP-08) ─────────────────────────────────────────────────────────

    @abstractmethod
    async def get_usage(
        self,
        start_date: datetime,
        end_date: datetime,
        *,
        cursor: str | None = None,
        limit: int = 100,
    ) -> UsagePage:
        """Fetch one page of historical usage from the provider's billing API.

        ``cursor`` resumes pagination from a previous call's ``next_cursor``.
        ``limit`` caps the page size (provider may return fewer records).

        Adapters for providers that do not expose a usage API (e.g. Ollama)
        should return an empty ``UsagePage`` with ``has_more=False``.
        """
        ...

    # ── Provider metadata (PH-04) ─────────────────────────────────────────────

    @abstractmethod
    def get_provider_info(self, health: HealthStatus | None = None) -> ProviderInfo:
        """Return a serialisable snapshot of the provider's identity and capabilities."""
        ...

    # ── Concrete helpers ──────────────────────────────────────────────────────

    @property
    def config(self) -> ProviderConfig:
        return self._config

    @property
    def display_name(self) -> str:
        return self._config.display_name
