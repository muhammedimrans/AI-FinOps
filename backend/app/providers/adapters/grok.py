"""Grok (xAI) provider adapter — EP-22 (validation), EP-06 (catalog/capabilities).

Authentication
--------------
``Authorization: Bearer <api_key>`` — OpenAI-compatible.

Live API calls
---------------
``GET /models`` — model discovery, used as the credential-validation probe.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import httpx

from app.http.auth import BearerTokenAuth
from app.http.client import ProviderHttpClient
from app.http.transport import HttpxTransport
from app.models.provider_connection import ProviderType
from app.providers.capabilities import ProviderCapabilities
from app.providers.config import ProviderConfig
from app.providers.credential import CredentialValidator, SecretResolver
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

_BASE_URL = "https://api.x.ai/v1"

_CAPABILITIES = ProviderCapabilities(
    supports_streaming=True,
    supports_tool_calling=True,
    supports_vision=True,
    supports_audio=False,
    supports_usage_api=True,
    has_rate_limits=True,
    requires_api_key=True,
    supports_oauth=False,
    supports_fine_tuning=False,
    supports_function_calling=True,
    max_context_window=131072,
    supported_model_ids=frozenset({"grok-2-1212", "grok-2-vision-1212", "grok-beta"}),
)

_MODELS: list[ModelMetadata] = [
    ModelMetadata(
        id="grok-2-1212",
        display_name="Grok 2",
        provider_type="grok",
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
        id="grok-2-vision-1212",
        display_name="Grok 2 Vision",
        provider_type="grok",
        context_window=32768,
        capabilities=frozenset(
            {
                ModelCapabilityFlag.STREAMING,
                ModelCapabilityFlag.VISION,
                ModelCapabilityFlag.TOOL_CALLING,
                ModelCapabilityFlag.FUNCTION_CALLING,
            }
        ),
    ),
    ModelMetadata(
        id="grok-beta",
        display_name="Grok Beta",
        provider_type="grok",
        context_window=131072,
        capabilities=frozenset(
            {
                ModelCapabilityFlag.STREAMING,
                ModelCapabilityFlag.TOOL_CALLING,
                ModelCapabilityFlag.FUNCTION_CALLING,
            }
        ),
    ),
]


class GrokProvider(AIProvider):
    """Grok (xAI) provider adapter (EP-22).

    Maintains a shared ``HttpxTransport`` so the httpx connection pool is
    reused across ``verify_auth`` and ``check_connection`` calls, matching
    the OpenAI/Anthropic adapter pattern (PH-01).
    """

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
            base_url=config.base_url or _BASE_URL,
            verify=True,
            mock_transport=http_transport,
        )

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.GROK

    @property
    def capabilities(self) -> ProviderCapabilities:
        return _CAPABILITIES

    @property
    def is_healthy(self) -> bool:
        return self._healthy

    def _build_client(self, api_key: str) -> ProviderHttpClient:
        return ProviderHttpClient(
            base_url=self._config.base_url or _BASE_URL,
            auth=BearerTokenAuth(api_key),
            provider_type="grok",
            timeout=self._config.timeout_seconds,
            transport=self._transport,
        )

    def _resolve_key(self) -> str:
        if self._config.api_key_ref is None:
            from app.providers.errors import AuthenticationError

            raise AuthenticationError(
                "Grok provider has no api_key_ref configured", provider_type="grok"
            )
        return SecretResolver.resolve(self._config.api_key_ref, provider_type="grok")

    async def verify_auth(self) -> bool:
        """Live GET /models — requires a valid key. Raises AuthenticationError on 401/403."""
        key = self._resolve_key()
        CredentialValidator.validate_grok_key(key)
        async with self._build_client(key) as client:
            await client.get("/models")
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

    async def check_capability(self, capability: str) -> bool:
        cap = capability.lower()
        return getattr(_CAPABILITIES, f"supports_{cap}", False) or getattr(
            _CAPABILITIES, cap, False
        )

    async def list_models(self) -> list[ModelMetadata]:
        return list(_MODELS)

    async def aclose(self) -> None:
        await self._transport.aclose()

    async def __aenter__(self) -> GrokProvider:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        raise NotImplementedError("Grok completion is implemented in EP-07")

    async def get_usage(
        self,
        start_date: datetime,
        end_date: datetime,
        *,
        cursor: str | None = None,
        limit: int = 100,
    ) -> UsagePage:
        """xAI does not publish a bulk usage-history API for third-party
        integrations as of this EP — there is no ``GET .../usage`` endpoint
        this adapter's API key can call to retrieve historical per-request
        token/cost data. An honest empty page is returned rather than
        fabricating events; see CLAUDE.md's EP-24.3 section for the full
        per-provider accounting. The sync pipeline (checkpoint, retry,
        scheduler) still runs normally for this provider.
        """
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
