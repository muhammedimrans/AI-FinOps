"""Tests for ProviderValidator (EP-22 Part 3/4).

Exercises the full dispatch + normalization path — config building via
``_build_config``, adapter selection via ``ProviderFactory``, and mapping
each ``app.providers.errors`` exception to the right
``ProviderValidationStatus`` — without any network calls. Each adapter's
``verify_auth`` is patched directly (the adapters themselves, including
their real HTTP call shape, are covered by ``test_ep07.py`` and the
per-provider mock-transport tests below for the 5 EP-22 adapters).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.models.provider_connection import (
    ProviderHealthStatus,
    ProviderType,
    ProviderValidationStatus,
)
from app.providers.adapters.azure_openai import AzureOpenAIProvider
from app.providers.adapters.google import GoogleProvider
from app.providers.adapters.grok import GrokProvider
from app.providers.adapters.ollama import OllamaProvider
from app.providers.adapters.openrouter import OpenRouterProvider
from app.providers.errors import (
    AuthenticationError,
    InternalProviderError,
    NetworkError,
    QuotaExceededError,
    RateLimitError,
)
from app.providers.validation import ProviderValidator


def _response(
    status_code: int, body: object = None, url: str = "https://example.test/"
) -> httpx.Response:
    import json

    resp = httpx.Response(status_code, content=json.dumps(body or {}).encode())
    resp.request = httpx.Request("GET", url)
    return resp


def _mock_transport(responses: list[httpx.Response]) -> httpx.MockTransport:
    it = iter(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        return next(it)

    return httpx.MockTransport(handler=handler)


class TestProviderValidatorHealthyAndErrorMapping:
    @pytest.mark.asyncio
    async def test_healthy_maps_to_healthy_status(self) -> None:
        validator = ProviderValidator()
        with patch(
            "app.providers.adapters.openai.OpenAIProvider.verify_auth",
            new=AsyncMock(return_value=True),
        ):
            result = await validator.validate(ProviderType.OPENAI, api_key="sk-" + "a" * 40)
        assert result.validation_status == ProviderValidationStatus.HEALTHY
        assert result.health_status == ProviderHealthStatus.HEALTHY
        assert result.is_healthy is True
        assert result.detail == "Connection healthy."

    @pytest.mark.asyncio
    async def test_authentication_error_maps_to_invalid_api_key(self) -> None:
        validator = ProviderValidator()
        with patch(
            "app.providers.adapters.openai.OpenAIProvider.verify_auth",
            new=AsyncMock(side_effect=AuthenticationError("Invalid API key or unauthorized")),
        ):
            result = await validator.validate(ProviderType.OPENAI, api_key="sk-bad")
        assert result.validation_status == ProviderValidationStatus.INVALID_API_KEY
        assert result.health_status == ProviderHealthStatus.CRITICAL
        # Normalized detail — never the raw exception text.
        assert result.detail == "The API key is invalid or has been revoked."

    @pytest.mark.asyncio
    async def test_forbidden_authentication_error_maps_to_unauthorized(self) -> None:
        validator = ProviderValidator()
        with patch(
            "app.providers.adapters.openai.OpenAIProvider.verify_auth",
            new=AsyncMock(side_effect=AuthenticationError("Access forbidden — check scope")),
        ):
            result = await validator.validate(ProviderType.OPENAI, api_key="sk-scoped")
        assert result.validation_status == ProviderValidationStatus.UNAUTHORIZED
        assert result.health_status == ProviderHealthStatus.CRITICAL

    @pytest.mark.asyncio
    async def test_rate_limit_error_maps_to_quota_exceeded(self) -> None:
        validator = ProviderValidator()
        with patch(
            "app.providers.adapters.openai.OpenAIProvider.verify_auth",
            new=AsyncMock(side_effect=RateLimitError()),
        ):
            result = await validator.validate(ProviderType.OPENAI, api_key="sk-" + "a" * 40)
        assert result.validation_status == ProviderValidationStatus.QUOTA_EXCEEDED
        assert result.health_status == ProviderHealthStatus.WARNING

    @pytest.mark.asyncio
    async def test_quota_exceeded_error_maps_to_quota_exceeded(self) -> None:
        validator = ProviderValidator()
        with patch(
            "app.providers.adapters.openai.OpenAIProvider.verify_auth",
            new=AsyncMock(side_effect=QuotaExceededError()),
        ):
            result = await validator.validate(ProviderType.OPENAI, api_key="sk-" + "a" * 40)
        assert result.validation_status == ProviderValidationStatus.QUOTA_EXCEEDED

    @pytest.mark.asyncio
    async def test_network_timeout_maps_to_timeout(self) -> None:
        validator = ProviderValidator()
        with patch(
            "app.providers.adapters.openai.OpenAIProvider.verify_auth",
            new=AsyncMock(side_effect=NetworkError("Request timed out")),
        ):
            result = await validator.validate(ProviderType.OPENAI, api_key="sk-" + "a" * 40)
        assert result.validation_status == ProviderValidationStatus.TIMEOUT
        assert result.health_status == ProviderHealthStatus.WARNING

    @pytest.mark.asyncio
    async def test_network_error_maps_to_network_failure(self) -> None:
        validator = ProviderValidator()
        with patch(
            "app.providers.adapters.openai.OpenAIProvider.verify_auth",
            new=AsyncMock(side_effect=NetworkError("Connection failed — DNS or refused")),
        ):
            result = await validator.validate(ProviderType.OPENAI, api_key="sk-" + "a" * 40)
        assert result.validation_status == ProviderValidationStatus.NETWORK_FAILURE

    @pytest.mark.asyncio
    async def test_internal_provider_error_maps_to_provider_unavailable(self) -> None:
        validator = ProviderValidator()
        with patch(
            "app.providers.adapters.openai.OpenAIProvider.verify_auth",
            new=AsyncMock(side_effect=InternalProviderError()),
        ):
            result = await validator.validate(ProviderType.OPENAI, api_key="sk-" + "a" * 40)
        assert result.validation_status == ProviderValidationStatus.PROVIDER_UNAVAILABLE
        assert result.health_status == ProviderHealthStatus.CRITICAL

    @pytest.mark.asyncio
    async def test_unsupported_provider_type_returns_invalid_api_key(self) -> None:
        validator = ProviderValidator()
        result = await validator.validate(ProviderType.COHERE, api_key="whatever")
        assert result.validation_status == ProviderValidationStatus.INVALID_API_KEY
        assert "No credential-validation support" in result.detail

    @pytest.mark.asyncio
    async def test_azure_without_base_url_fails_config_validation(self) -> None:
        validator = ProviderValidator()
        result = await validator.validate(
            ProviderType.AZURE_OPENAI, api_key="a" * 32, base_url=None
        )
        assert result.validation_status == ProviderValidationStatus.INVALID_API_KEY
        assert "base_url" in result.detail

    @pytest.mark.asyncio
    async def test_ollama_validates_without_any_api_key(self) -> None:
        """Ollama requires no credential — api_key=None must not itself cause failure."""
        validator = ProviderValidator()
        with patch(
            "app.providers.adapters.ollama.OllamaProvider.verify_auth",
            new=AsyncMock(return_value=True),
        ):
            result = await validator.validate(ProviderType.OLLAMA, api_key=None)
        assert result.validation_status == ProviderValidationStatus.HEALTHY


class TestNewAdapterLiveHttpShape:
    """One hermetic, mocked-transport, real-HTTP-call test per EP-22 adapter
    (Grok, OpenRouter, Google, Azure OpenAI, Ollama) — confirms verify_auth
    actually performs the live call named in CLAUDE.md §13's probe table,
    not just that ProviderValidator's dispatch logic works."""

    @pytest.mark.asyncio
    async def test_grok_verify_auth_calls_models_endpoint(self) -> None:
        from app.providers.config import GrokConfig, SecretReference, SecretStoreType

        config = GrokConfig(
            provider_type="grok",
            display_name="Grok",
            api_key_ref=SecretReference(secret_store=SecretStoreType.ENV, lookup_key="TEST_GROK"),
        )
        transport = _mock_transport([_response(200, {"data": []})])
        provider = GrokProvider(config, http_transport=transport)
        with patch.dict("os.environ", {"TEST_GROK": "xai-" + "a" * 20}):
            assert await provider.verify_auth() is True
        await provider.aclose()

    @pytest.mark.asyncio
    async def test_grok_401_raises_authentication_error(self) -> None:
        from app.providers.config import GrokConfig, SecretReference, SecretStoreType

        config = GrokConfig(
            provider_type="grok",
            display_name="Grok",
            api_key_ref=SecretReference(secret_store=SecretStoreType.ENV, lookup_key="TEST_GROK2"),
        )
        transport = _mock_transport([_response(401)])
        provider = GrokProvider(config, http_transport=transport)
        with patch.dict("os.environ", {"TEST_GROK2": "xai-" + "a" * 20}):
            with pytest.raises(AuthenticationError):
                await provider.verify_auth()
        await provider.aclose()

    @pytest.mark.asyncio
    async def test_openrouter_verify_auth_calls_models_endpoint(self) -> None:
        from app.providers.config import OpenRouterConfig, SecretReference, SecretStoreType

        config = OpenRouterConfig(
            provider_type="openrouter",
            display_name="OpenRouter",
            api_key_ref=SecretReference(secret_store=SecretStoreType.ENV, lookup_key="TEST_OR"),
        )
        transport = _mock_transport([_response(200, {"data": []})])
        provider = OpenRouterProvider(config, http_transport=transport)
        with patch.dict("os.environ", {"TEST_OR": "sk-or-" + "a" * 20}):
            assert await provider.verify_auth() is True
        await provider.aclose()

    @pytest.mark.asyncio
    async def test_google_verify_auth_sends_key_as_query_param(self) -> None:
        from app.providers.config import GoogleConfig, SecretReference, SecretStoreType

        captured: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["query"] = str(request.url.params)
            return _response(200, {"models": []})

        config = GoogleConfig(
            provider_type="google",
            display_name="Google Gemini",
            api_key_ref=SecretReference(secret_store=SecretStoreType.ENV, lookup_key="TEST_GOOGLE"),
        )
        provider = GoogleProvider(config, http_transport=httpx.MockTransport(handler))
        with patch.dict("os.environ", {"TEST_GOOGLE": "AIza" + "a" * 30}):
            assert await provider.verify_auth() is True
        assert "key=" in captured["query"]
        await provider.aclose()

    @pytest.mark.asyncio
    async def test_azure_verify_auth_calls_deployments_endpoint(self) -> None:
        from app.providers.config import AzureOpenAIConfig, SecretReference, SecretStoreType

        config = AzureOpenAIConfig(
            provider_type="azure_openai",
            display_name="Azure OpenAI",
            azure_endpoint="https://my-resource.openai.azure.com",
            api_key_ref=SecretReference(secret_store=SecretStoreType.ENV, lookup_key="TEST_AZURE"),
        )
        transport = _mock_transport([_response(200, {"data": []})])
        provider = AzureOpenAIProvider(config, http_transport=transport)
        with patch.dict("os.environ", {"TEST_AZURE": "a" * 32}):
            assert await provider.verify_auth() is True
        await provider.aclose()

    @pytest.mark.asyncio
    async def test_ollama_verify_auth_calls_tags_endpoint_with_no_auth(self) -> None:
        from app.providers.config import OllamaConfig

        config = OllamaConfig(provider_type="ollama", display_name="Ollama")
        transport = _mock_transport([_response(200, {"models": []})])
        provider = OllamaProvider(config, http_transport=transport)
        assert await provider.verify_auth() is True
        await provider.aclose()

    @pytest.mark.asyncio
    async def test_ollama_unreachable_raises_network_error(self) -> None:
        from app.providers.config import OllamaConfig

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused", request=request)

        config = OllamaConfig(provider_type="ollama", display_name="Ollama")
        provider = OllamaProvider(config, http_transport=httpx.MockTransport(handler))
        with pytest.raises(NetworkError):
            await provider.verify_auth()
        await provider.aclose()
