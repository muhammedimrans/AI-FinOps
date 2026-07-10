"""Google Gemini provider adapter — EP-22 (validation), EP-06 (catalog/capabilities).

Authentication
--------------
API key travels as a ``?key=`` query parameter (Google's AI Studio / Gemini
API convention), not an Authorization header — see ``NullAuth`` in
``app.http.auth``; the key is passed via ``params`` on the request instead.

Live API calls
---------------
``GET /v1beta/models?key=<api_key>`` — the model discovery endpoint named in
the EP-22 spec, doubling as the credential-validation probe.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import httpx

from app.http.auth import NullAuth
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

_BASE_URL = "https://generativelanguage.googleapis.com"

_CAPABILITIES = ProviderCapabilities(
    supports_streaming=True,
    supports_tool_calling=True,
    supports_vision=True,
    supports_audio=True,
    supports_usage_api=True,
    has_rate_limits=True,
    requires_api_key=True,
    supports_oauth=True,
    supports_fine_tuning=True,
    supports_function_calling=True,
    max_context_window=2000000,
    supported_model_ids=frozenset(
        {"gemini-1.5-pro", "gemini-1.5-flash", "gemini-1.5-flash-8b", "gemini-2.0-flash"}
    ),
)

_MODELS: list[ModelMetadata] = [
    ModelMetadata(
        id="gemini-1.5-pro",
        display_name="Gemini 1.5 Pro",
        provider_type="google",
        context_window=2000000,
        max_output_tokens=8192,
        capabilities=frozenset(
            {
                ModelCapabilityFlag.STREAMING,
                ModelCapabilityFlag.TOOL_CALLING,
                ModelCapabilityFlag.VISION,
                ModelCapabilityFlag.AUDIO,
                ModelCapabilityFlag.FUNCTION_CALLING,
            }
        ),
    ),
    ModelMetadata(
        id="gemini-1.5-flash",
        display_name="Gemini 1.5 Flash",
        provider_type="google",
        context_window=1000000,
        max_output_tokens=8192,
        capabilities=frozenset(
            {
                ModelCapabilityFlag.STREAMING,
                ModelCapabilityFlag.TOOL_CALLING,
                ModelCapabilityFlag.VISION,
                ModelCapabilityFlag.FUNCTION_CALLING,
            }
        ),
    ),
    ModelMetadata(
        id="gemini-1.5-flash-8b",
        display_name="Gemini 1.5 Flash 8B",
        provider_type="google",
        context_window=1000000,
        max_output_tokens=8192,
        capabilities=frozenset(
            {
                ModelCapabilityFlag.STREAMING,
                ModelCapabilityFlag.TOOL_CALLING,
                ModelCapabilityFlag.VISION,
                ModelCapabilityFlag.FUNCTION_CALLING,
            }
        ),
    ),
    ModelMetadata(
        id="gemini-2.0-flash",
        display_name="Gemini 2.0 Flash",
        provider_type="google",
        context_window=1000000,
        max_output_tokens=8192,
        capabilities=frozenset(
            {
                ModelCapabilityFlag.STREAMING,
                ModelCapabilityFlag.TOOL_CALLING,
                ModelCapabilityFlag.VISION,
                ModelCapabilityFlag.AUDIO,
                ModelCapabilityFlag.FUNCTION_CALLING,
            }
        ),
    ),
]


class GoogleProvider(AIProvider):
    """Google Gemini provider adapter (EP-22)."""

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
        return ProviderType.GOOGLE

    @property
    def capabilities(self) -> ProviderCapabilities:
        return _CAPABILITIES

    @property
    def is_healthy(self) -> bool:
        return self._healthy

    def _build_client(self) -> ProviderHttpClient:
        return ProviderHttpClient(
            base_url=self._config.base_url or _BASE_URL,
            auth=NullAuth(),
            provider_type="google",
            timeout=self._config.timeout_seconds,
            transport=self._transport,
        )

    def _resolve_key(self) -> str:
        if self._config.api_key_ref is None:
            from app.providers.errors import AuthenticationError

            raise AuthenticationError(
                "Google provider has no api_key_ref configured", provider_type="google"
            )
        return SecretResolver.resolve(self._config.api_key_ref, provider_type="google")

    async def verify_auth(self) -> bool:
        """Live GET /v1beta/models?key=<key> — raises AuthenticationError on 401/403."""
        key = self._resolve_key()
        CredentialValidator.validate_google_key(key)
        async with self._build_client() as client:
            await client.get("/v1beta/models", params={"key": key})
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

    async def __aenter__(self) -> GoogleProvider:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        raise NotImplementedError("Google completion is implemented in EP-07")

    async def get_usage(
        self,
        start_date: datetime,
        end_date: datetime,
        *,
        cursor: str | None = None,
        limit: int = 100,
    ) -> UsagePage:
        """No bulk usage-history endpoint exists for an AI-Studio API key.

        Google's per-request usage/cost data is only available through
        Cloud Billing export (BigQuery), which requires a GCP project and
        service-account credentials distinct from the Gemini API key this
        connection stores — there is no ``GET .../usage`` call this
        adapter's credential can make. Returning an honest empty page
        (rather than fabricating events) matches this codebase's standing
        "no fake functionality" rule; see CLAUDE.md's EP-24.3 section for
        the full per-provider accounting. The sync pipeline (checkpoint,
        retry, scheduler) still runs normally for this provider — it is
        simply the correct, honest outcome that runs 0 records every time.
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
