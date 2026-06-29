"""Provider connectivity endpoints — EP-07.

POST /providers/{provider}/test  — live auth + connectivity probe
GET  /providers/{provider}/models — model discovery (live API)
GET  /providers/{provider}/info   — provider metadata (static + health)
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.providers.config import (
    AnthropicConfig,
    OpenAIConfig,
    SecretReference,
    SecretStoreType,
)
from app.providers.errors import AuthenticationError, InvalidRequestError, ProviderError
from app.providers.info import ProviderInfo
from app.providers.interface import AIProvider
from app.providers.models import HealthStatus
from app.schemas.providers import ModelsResponse, TestConnectionResponse

router = APIRouter(prefix="/providers", tags=["providers"])

_SUPPORTED_PROVIDERS = {"openai", "anthropic"}


def _get_openai_provider(env_key: str = "OPENAI_API_KEY") -> AIProvider:
    from app.providers.adapters.openai import OpenAIProvider

    config = OpenAIConfig(
        provider_type="openai",
        display_name="OpenAI",
        api_key_ref=SecretReference(
            secret_store=SecretStoreType.ENV,
            secret_key=env_key,
        ),
    )
    return OpenAIProvider(config)


def _get_anthropic_provider(env_key: str = "ANTHROPIC_API_KEY") -> AIProvider:
    from app.providers.adapters.anthropic import AnthropicProvider

    config = AnthropicConfig(
        provider_type="anthropic",
        display_name="Anthropic",
        api_key_ref=SecretReference(
            secret_store=SecretStoreType.ENV,
            secret_key=env_key,
        ),
    )
    return AnthropicProvider(config)


def _require_supported(provider: str) -> None:
    if provider not in _SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Provider {provider!r} is not supported. "
                f"Supported: {sorted(_SUPPORTED_PROVIDERS)}"
            ),
        )


@router.post(
    "/{provider}/test",
    response_model=TestConnectionResponse,
    summary="Test provider connectivity and authentication",
    description=(
        "Makes a live API call to verify that the provider's API key is configured "
        "and the provider is reachable. Does not stream or complete any request."
    ),
)
async def test_connection(provider: str) -> TestConnectionResponse:
    _require_supported(provider)
    try:
        if provider == "openai":
            adapter = _get_openai_provider()
        else:
            adapter = _get_anthropic_provider()

        conn_status = await adapter.check_connection()
        return TestConnectionResponse(
            provider=provider,
            status=conn_status,
            auth_valid=conn_status.is_connected,
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
async def list_models(provider: str) -> ModelsResponse:
    _require_supported(provider)
    try:
        if provider == "openai":
            adapter = _get_openai_provider()
        else:
            adapter = _get_anthropic_provider()

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
async def get_provider_info(provider: str) -> ProviderInfo:
    _require_supported(provider)

    if provider == "openai":
        from app.providers.adapters.openai import OpenAIProvider

        config = OpenAIConfig(provider_type="openai", display_name="OpenAI")
        adapter = OpenAIProvider(config)
    else:
        from app.providers.adapters.anthropic import AnthropicProvider

        config = AnthropicConfig(provider_type="anthropic", display_name="Anthropic")
        adapter = AnthropicProvider(config)

    return adapter.get_provider_info(health=HealthStatus.UNKNOWN)
