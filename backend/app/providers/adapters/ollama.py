"""Ollama provider adapter — EP-22 (validation), EP-06 (catalog/capabilities).

Authentication
--------------
None — Ollama is self-hosted and ``requires_api_key=False``
(``OllamaConfig``). "Validation" for Ollama means confirming the local/LAN
server is reachable, not verifying a credential.

Live API calls
---------------
``GET /api/tags`` — the local tags endpoint named in the EP-22 spec; lists
locally-pulled models and doubles as the reachability probe.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import httpx

from app.http.auth import NullAuth
from app.http.client import ProviderHttpClient
from app.http.transport import HttpxTransport
from app.models.provider_connection import ProviderType
from app.providers.capabilities import ProviderCapabilities
from app.providers.config import ProviderConfig
from app.providers.interface import AIProvider
from app.providers.models import (
    ConnectionStatus,
    HealthStatus,
    ModelCapabilityFlag,
    ModelMetadata,
    ProviderRequest,
    ProviderResponse,
)

if TYPE_CHECKING:
    from app.providers.info import ProviderInfo
    from app.providers.models import UsagePage

_DEFAULT_BASE_URL = "http://localhost:11434"

_CAPABILITIES = ProviderCapabilities(
    supports_streaming=True,
    supports_tool_calling=True,
    supports_vision=True,
    supports_audio=False,
    supports_usage_api=False,
    has_rate_limits=False,
    requires_api_key=False,
    supports_oauth=False,
    supports_fine_tuning=False,
    supports_function_calling=True,
    max_context_window=None,
    supported_model_ids=frozenset(
        {"llama3.2", "llama3.1", "mistral", "codellama", "phi3", "gemma2"}
    ),
)

_MODELS: list[ModelMetadata] = [
    ModelMetadata(
        id="llama3.2",
        display_name="Llama 3.2",
        provider_type="ollama",
        context_window=128000,
        capabilities=frozenset(
            {
                ModelCapabilityFlag.STREAMING,
                ModelCapabilityFlag.TOOL_CALLING,
                ModelCapabilityFlag.FUNCTION_CALLING,
            }
        ),
    ),
    ModelMetadata(
        id="llama3.1",
        display_name="Llama 3.1",
        provider_type="ollama",
        context_window=131072,
        capabilities=frozenset(
            {
                ModelCapabilityFlag.STREAMING,
                ModelCapabilityFlag.TOOL_CALLING,
                ModelCapabilityFlag.FUNCTION_CALLING,
            }
        ),
    ),
    ModelMetadata(
        id="mistral",
        display_name="Mistral",
        provider_type="ollama",
        context_window=32768,
        capabilities=frozenset(
            {
                ModelCapabilityFlag.STREAMING,
                ModelCapabilityFlag.TOOL_CALLING,
                ModelCapabilityFlag.FUNCTION_CALLING,
            }
        ),
    ),
    ModelMetadata(
        id="codellama",
        display_name="Code Llama",
        provider_type="ollama",
        context_window=16384,
        capabilities=frozenset({ModelCapabilityFlag.STREAMING}),
    ),
    ModelMetadata(
        id="phi3",
        display_name="Phi-3",
        provider_type="ollama",
        context_window=128000,
        capabilities=frozenset(
            {
                ModelCapabilityFlag.STREAMING,
                ModelCapabilityFlag.TOOL_CALLING,
                ModelCapabilityFlag.FUNCTION_CALLING,
            }
        ),
    ),
    ModelMetadata(
        id="gemma2",
        display_name="Gemma 2",
        provider_type="ollama",
        context_window=8192,
        capabilities=frozenset({ModelCapabilityFlag.STREAMING}),
    ),
]


class OllamaProvider(AIProvider):
    """Ollama (self-hosted) provider adapter (EP-22)."""

    def __init__(
        self,
        config: ProviderConfig,
        *,
        http_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(config)
        self._healthy: bool = False
        self._last_checked: datetime | None = None
        self._transport = HttpxTransport(
            base_url=config.base_url or _DEFAULT_BASE_URL,
            verify=False,
            mock_transport=http_transport,
        )

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.OLLAMA

    @property
    def capabilities(self) -> ProviderCapabilities:
        return _CAPABILITIES

    @property
    def is_healthy(self) -> bool:
        return self._healthy

    def _build_client(self) -> ProviderHttpClient:
        return ProviderHttpClient(
            base_url=self._config.base_url or _DEFAULT_BASE_URL,
            auth=NullAuth(),
            provider_type="ollama",
            timeout=self._config.timeout_seconds,
            transport=self._transport,
        )

    async def verify_auth(self) -> bool:
        """Live GET /api/tags — confirms the local/LAN server is reachable.

        Ollama has no credential to validate; "auth" here is reachability.
        Raises NetworkError (mapped to PROVIDER_UNAVAILABLE by ProviderValidator)
        if the server cannot be reached.
        """
        async with self._build_client() as client:
            await client.get("/api/tags")
        return True

    async def check_connection(self) -> ConnectionStatus:
        start = time.monotonic()
        try:
            await self.verify_auth()
            latency = round((time.monotonic() - start) * 1000, 2)
            self._healthy = True
            self._last_checked = datetime.now(UTC)
            return ConnectionStatus(
                is_connected=True,
                health_status=HealthStatus.HEALTHY,
                latency_ms=latency,
                checked_at=self._last_checked,
            )
        except Exception as exc:
            latency = round((time.monotonic() - start) * 1000, 2)
            self._healthy = False
            self._last_checked = datetime.now(UTC)
            return ConnectionStatus(
                is_connected=False,
                health_status=HealthStatus.UNHEALTHY,
                latency_ms=latency,
                error_message=str(exc),
                checked_at=self._last_checked,
            )

    async def list_models(self) -> list[ModelMetadata]:
        """Return the live locally-pulled model list when reachable, else the static catalog."""
        try:
            async with self._build_client() as client:
                data: dict[str, Any] = await client.get("/api/tags")
        except Exception:
            return list(_MODELS)
        live: list[ModelMetadata] = []
        for entry in data.get("models", []):
            name = entry.get("name")
            if not name:
                continue
            live.append(
                ModelMetadata(
                    id=name,
                    display_name=name,
                    provider_type="ollama",
                    capabilities=frozenset({ModelCapabilityFlag.STREAMING}),
                )
            )
        return live or list(_MODELS)

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        raise NotImplementedError("Ollama completion is implemented in EP-07")

    async def check_capability(self, capability: str) -> bool:
        cap = capability.lower()
        return getattr(_CAPABILITIES, f"supports_{cap}", False) or getattr(
            _CAPABILITIES, cap, False
        )

    async def aclose(self) -> None:
        await self._transport.aclose()

    async def __aenter__(self) -> OllamaProvider:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()

    async def get_usage(
        self,
        start_date: datetime,
        end_date: datetime,
        *,
        cursor: str | None = None,
        limit: int = 100,
    ) -> UsagePage:
        from app.providers.models import UsagePage

        return UsagePage()

    def get_provider_info(self, health: HealthStatus | None = None) -> ProviderInfo:
        from app.providers.info import ProviderInfo

        return ProviderInfo.from_capabilities(
            provider=self.provider_type.value,
            display_name=self._config.display_name,
            capabilities=_CAPABILITIES,
            health=health if health is not None else HealthStatus.UNKNOWN,
        )
