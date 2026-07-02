"""Provider connectivity endpoints — EP-07 / EP-07-PH.

POST /providers/{provider}/test  — live auth + connectivity probe
GET  /providers/{provider}/models — model discovery (live API)
GET  /providers/{provider}/info   — provider metadata (static + health)

Changes from EP-07 base
-----------------------
PH-03  Adapters are created via ProviderFactory + ProviderRegistry rather than
       direct instantiation.  All EP-06.5 validation (provider_type cross-check,
       registry lookup, config validation) is applied automatically.
PH-05  Supported provider set is derived from ProviderType enum members — no
       free-form string set to maintain manually.
PH-06  test_connection calls verify_auth() directly so authentication failures
       surface as HTTP 401 rather than HTTP 200 with auth_valid=false in the body.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status

from app.auth.dependencies import CurrentUser
from app.models.provider_connection import ProviderType
from app.providers.config import (
    AnthropicConfig,
    OpenAIConfig,
    SecretReference,
    SecretStoreType,
)
from app.providers.errors import AuthenticationError, InvalidRequestError, ProviderError
from app.providers.factory import ProviderFactory
from app.providers.info import ProviderInfo
from app.providers.interface import AIProvider
from app.providers.models import ConnectionStatus, HealthStatus
from app.providers.registry import get_registry
from app.schemas.providers import ModelsResponse, TestConnectionResponse

router = APIRouter(prefix="/providers", tags=["providers"])

# Typed frozenset derived from ProviderType enum — single source of truth (PH-05).
# Only list providers that have production-ready adapters.  Add a new member here
# when its adapter is promoted from stub to production.
_PRODUCTION_PROVIDERS: frozenset[ProviderType] = frozenset(
    {
        ProviderType.OPENAI,
        ProviderType.ANTHROPIC,
    }
)


def _require_supported(provider: str) -> ProviderType:
    """Validate provider string and return its ProviderType.

    Returns HTTP 404 for:
    - Unknown provider names (not a ProviderType enum value)
    - Known ProviderType values whose adapter is not yet production-ready
    """
    try:
        pt = ProviderType(provider)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Provider {provider!r} is not supported. "
                f"Supported: {sorted(p.value for p in _PRODUCTION_PROVIDERS)}"
            ),
        )
    if pt not in _PRODUCTION_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Provider {provider!r} adapter is not yet production-ready. "
                f"Supported: {sorted(p.value for p in _PRODUCTION_PROVIDERS)}"
            ),
        )
    return pt


def _make_config_with_key(pt: ProviderType) -> OpenAIConfig | AnthropicConfig:
    """Build provider config with default env-var key reference."""
    match pt:
        case ProviderType.OPENAI:
            return OpenAIConfig(
                provider_type=pt.value,
                display_name="OpenAI",
                api_key_ref=SecretReference(
                    secret_store=SecretStoreType.ENV,
                    secret_key="OPENAI_API_KEY",
                ),
            )
        case ProviderType.ANTHROPIC:
            return AnthropicConfig(
                provider_type=pt.value,
                display_name="Anthropic",
                api_key_ref=SecretReference(
                    secret_store=SecretStoreType.ENV,
                    secret_key="ANTHROPIC_API_KEY",
                ),
            )
        case _:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No config builder for {pt.value!r}",
            )


def _make_config_no_key(pt: ProviderType) -> OpenAIConfig | AnthropicConfig:
    """Build provider config without an api_key_ref (for info endpoint)."""
    match pt:
        case ProviderType.OPENAI:
            return OpenAIConfig(provider_type=pt.value, display_name="OpenAI")
        case ProviderType.ANTHROPIC:
            return AnthropicConfig(provider_type=pt.value, display_name="Anthropic")
        case _:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No config builder for {pt.value!r}",
            )


def _get_adapter(pt: ProviderType, *, with_key: bool) -> AIProvider:
    """Instantiate a provider adapter via ProviderFactory (PH-03)."""
    config = _make_config_with_key(pt) if with_key else _make_config_no_key(pt)
    return ProviderFactory(get_registry()).create(config)


@router.post(
    "/{provider}/test",
    response_model=TestConnectionResponse,
    summary="Test provider connectivity and authentication",
    description=(
        "Makes a live API call to verify that the provider's API key is configured "
        "and the provider is reachable.  Returns HTTP 401 if authentication fails, "
        "HTTP 502 for provider-side network or server errors.  "
        "Does not stream or complete any request."
    ),
)
async def test_connection(provider: str, _user: CurrentUser) -> TestConnectionResponse:
    pt = _require_supported(provider)
    adapter = _get_adapter(pt, with_key=True)
    try:
        start = time.monotonic()
        await adapter.verify_auth()
        latency_ms = round((time.monotonic() - start) * 1000, 2)
        return TestConnectionResponse(
            provider=provider,
            status=ConnectionStatus(
                is_connected=True,
                health_status=HealthStatus.HEALTHY,
                latency_ms=latency_ms,
                checked_at=datetime.now(UTC),
            ),
            auth_valid=True,
        )
    except (AuthenticationError, InvalidRequestError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    except ProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.get(
    "/{provider}/models",
    response_model=ModelsResponse,
    summary="List available models for a provider",
    description=(
        "Fetches the live model list from the provider API. "
        "Requires the provider's API key to be set in the environment."
    ),
)
async def list_models(provider: str, _user: CurrentUser) -> ModelsResponse:
    pt = _require_supported(provider)
    adapter = _get_adapter(pt, with_key=True)
    try:
        models = await adapter.list_models()
        return ModelsResponse(
            provider=provider,
            models=models,
            count=len(models),
        )
    except (AuthenticationError, InvalidRequestError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    except ProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.get(
    "/{provider}/info",
    response_model=ProviderInfo,
    summary="Get provider metadata and capabilities",
    description=(
        "Returns static provider metadata including capabilities, supported models, "
        "and last-known health status. Does not make a live API call."
    ),
)
async def get_provider_info(provider: str, _user: CurrentUser) -> ProviderInfo:
    pt = _require_supported(provider)
    adapter = _get_adapter(pt, with_key=False)
    return adapter.get_provider_info(health=HealthStatus.UNKNOWN)
