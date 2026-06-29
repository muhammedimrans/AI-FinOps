"""Health check interfaces — F-031."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.providers.models import ConnectionStatus


class HealthCheckInterface(ABC):
    @abstractmethod
    async def check_connection(self) -> ConnectionStatus: ...

    @abstractmethod
    async def verify_auth(self) -> bool: ...

    @abstractmethod
    async def check_capability(self, capability: str) -> bool: ...

    @property
    @abstractmethod
    def is_healthy(self) -> bool: ...
