"""OpenAI provider adapter — F-034 (EP-07) / F-042 (EP-08).

Implements verify_auth, check_connection, is_healthy, list_models,
check_capability, get_provider_info, and get_usage.

Usage collection (EP-08)
------------------------
``get_usage()`` calls ``GET /v1/organization/usage/completions`` with
``start_time`` / ``end_time`` UNIX timestamps and a ``page`` cursor.
Each response item is normalized by ``OpenAIUsageNormalizer`` into a
provider-agnostic ``NormalizedUsageEvent``.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

import httpx

from app.http.auth import BearerTokenAuth
from app.http.client import ProviderHttpClient
from app.http.transport import HttpxTransport
from app.models.provider_connection import ProviderType
from app.providers.capabilities import ProviderCapabilities
from app.providers.config import ProviderConfig
from app.providers.credential import CredentialValidator, SecretResolver
from app.providers.info import ProviderInfo
from app.providers.interface import AIProvider
from app.providers.models import (
    ConnectionStatus,
    HealthStatus,
    ModelCapabilityFlag,
    ModelMetadata,
    ProviderRequest,
    ProviderResponse,
    UsagePage,
)

_BASE_URL = "https://api.openai.com"
_API_VERSION = "v1"
_DOCS_URL = "https://platform.openai.com/docs"

_CAPABILITIES = ProviderCapabilities(
    supports_streaming=True,
    supports_tool_calling=True,
    supports_vision=True,
    supports_audio=True,
    supports_usage_api=True,
    has_rate_limits=True,
    requires_api_key=True,
    supports_oauth=False,
    supports_fine_tuning=True,
    supports_function_calling=True,
    max_context_window=128000,
    supported_model_ids=frozenset({"gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"}),
)

# Static enrichment for well-known models; live API provides the full id list.
_MODEL_ENRICHMENT: dict[str, dict[str, Any]] = {
    "gpt-4o": {
        "display_name": "GPT-4o",
        "context_window": 128000,
        "capabilities": frozenset(
            {
                ModelCapabilityFlag.STREAMING,
                ModelCapabilityFlag.TOOL_CALLING,
                ModelCapabilityFlag.VISION,
                ModelCapabilityFlag.FUNCTION_CALLING,
            }
        ),
    },
    "gpt-4o-mini": {
        "display_name": "GPT-4o Mini",
        "context_window": 128000,
        "capabilities": frozenset(
            {
                ModelCapabilityFlag.STREAMING,
                ModelCapabilityFlag.TOOL_CALLING,
                ModelCapabilityFlag.VISION,
                ModelCapabilityFlag.FUNCTION_CALLING,
            }
        ),
    },
    "gpt-4-turbo": {
        "display_name": "GPT-4 Turbo",
        "context_window": 128000,
        "capabilities": frozenset(
            {
                ModelCapabilityFlag.STREAMING,
                ModelCapabilityFlag.TOOL_CALLING,
                ModelCapabilityFlag.FUNCTION_CALLING,
            }
        ),
    },
    "gpt-3.5-turbo": {
        "display_name": "GPT-3.5 Turbo",
        "context_window": 16385,
        "capabilities": frozenset({ModelCapabilityFlag.STREAMING}),
        "is_deprecated": True,
    },
}


def _enrich_model(model_id: str) -> ModelMetadata:
    enrichment = _MODEL_ENRICHMENT.get(model_id, {})
    return ModelMetadata(
        id=model_id,
        display_name=enrichment.get("display_name", model_id),
        provider_type="openai",
        context_window=enrichment.get("context_window"),
        capabilities=enrichment.get("capabilities", frozenset()),
        is_deprecated=enrichment.get("is_deprecated", False),
    )


class OpenAIProvider(AIProvider):
    """Production OpenAI provider adapter (EP-07).

    Maintains a shared ``HttpxTransport`` so the httpx connection pool is reused
    across ``verify_auth``, ``list_models``, and ``check_connection`` calls.
    """

    def __init__(
        self,
        config: ProviderConfig,
        *,
        http_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(config)
        self._http_transport = http_transport
        self._healthy: bool = False
        self._last_checked: datetime | None = None
        # Shared transport — one httpx.AsyncClient per adapter instance (PH-01).
        self._transport = HttpxTransport(
            base_url=config.base_url or _BASE_URL,
            verify=True,
            mock_transport=http_transport,
        )

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.OPENAI

    @property
    def capabilities(self) -> ProviderCapabilities:
        return _CAPABILITIES

    @property
    def is_healthy(self) -> bool:
        return self._healthy

    def _build_client(self, api_key: str) -> ProviderHttpClient:
        """Return a ProviderHttpClient backed by the shared transport."""
        return ProviderHttpClient(
            base_url=self._config.base_url or _BASE_URL,
            auth=BearerTokenAuth(api_key),
            provider_type="openai",
            timeout=self._config.timeout_seconds,
            transport=self._transport,  # shared; aclose() is a no-op on this client
        )

    def _resolve_key(self) -> str:
        if self._config.api_key_ref is None:
            from app.providers.errors import AuthenticationError

            raise AuthenticationError(
                "OpenAI provider has no api_key_ref configured",
                provider_type="openai",
            )
        return SecretResolver.resolve(self._config.api_key_ref, provider_type="openai")

    async def verify_auth(self) -> bool:
        """Make a live API call to confirm the key is valid.

        Uses GET /v1/models — cheap, always available, requires a valid key.
        Returns True on success, raises AuthenticationError on 401/403.
        """
        key = self._resolve_key()
        CredentialValidator.validate_openai_key(key)
        async with self._build_client(key) as client:
            await client.get("/v1/models")
        return True

    async def check_connection(self) -> ConnectionStatus:
        """Probe the OpenAI API and cache the health state."""
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
        """Fetch live model list from the API and enrich with static metadata."""
        key = self._resolve_key()
        CredentialValidator.validate_openai_key(key)
        async with self._build_client(key) as client:
            data = await client.get("/v1/models")
        raw_models: list[dict[str, Any]] = data.get("data", [])
        return [_enrich_model(m["id"]) for m in raw_models if "id" in m]

    def get_provider_info(self, health: HealthStatus | None = None) -> ProviderInfo:
        return ProviderInfo.from_capabilities(
            provider="openai",
            display_name=self._config.display_name,
            capabilities=_CAPABILITIES,
            health=(
                health
                if health is not None
                else (HealthStatus.HEALTHY if self._healthy else HealthStatus.UNKNOWN)
            ),
            api_version=_API_VERSION,
            documentation_url=_DOCS_URL,
        )

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        raise NotImplementedError("OpenAI completion is implemented in a later EP")

    async def get_usage(
        self,
        start_date: datetime,
        end_date: datetime,
        *,
        cursor: str | None = None,
        limit: int = 100,
    ) -> UsagePage:
        """Fetch one page of usage from GET /v1/organization/usage/completions.

        Response shape (per item in ``data``):
            {"start_time": int, "model": str, "input_tokens": int,
             "output_tokens": int, "num_model_requests": int}
        ``has_more`` and ``next_page`` control pagination.
        """
        from app.usage.normalizer import OpenAIUsageNormalizer

        key = self._resolve_key()
        normalizer = OpenAIUsageNormalizer()

        params: dict[str, Any] = {
            "start_time": int(start_date.timestamp()),
            "end_time": int(end_date.timestamp()),
            "limit": min(limit, 1000),
        }
        if cursor:
            params["page"] = cursor

        async with self._build_client(key) as client:
            raw = await client.get("/v1/organization/usage/completions", params=params)

        items: list[dict[str, Any]] = raw.get("data", [])
        events = [normalizer.normalize(item) for item in items]
        next_cursor: str | None = raw.get("next_page") or None
        has_more: bool = bool(raw.get("has_more", False))

        return UsagePage(events=events, next_cursor=next_cursor, has_more=has_more)

    async def aclose(self) -> None:
        """Close the shared transport and its connection pool."""
        await self._transport.aclose()

    async def __aenter__(self) -> OpenAIProvider:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()
