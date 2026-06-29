"""EP-06 — AI Provider Framework tests."""

from __future__ import annotations

from datetime import UTC

import pytest

from app.models.provider_connection import ProviderType
from app.providers import (
    AIProvider,
    ProviderCapabilities,
    ProviderFactory,
    ProviderRegistry,
)
from app.providers.adapters.anthropic import AnthropicProvider
from app.providers.adapters.azure_openai import AzureOpenAIProvider
from app.providers.adapters.google import GoogleProvider
from app.providers.adapters.grok import GrokProvider
from app.providers.adapters.ollama import OllamaProvider
from app.providers.adapters.openai import OpenAIProvider
from app.providers.adapters.openrouter import OpenRouterProvider
from app.providers.config import (
    AnthropicConfig,
    AzureOpenAIConfig,
    GoogleConfig,
    GrokConfig,
    OllamaConfig,
    OpenAIConfig,
    OpenRouterConfig,
    ProviderConfig,
    SecretReference,
)
from app.providers.errors import (
    AuthenticationError,
    InternalProviderError,
    InvalidRequestError,
    NetworkError,
    ProviderError,
    QuotaExceededError,
    RateLimitError,
)
from app.providers.models import (
    ConnectionStatus,
    HealthStatus,
    ModelCapabilityFlag,
    ModelMetadata,
    ProviderRequest,
    ProviderResponse,
    UsageData,
)
from app.providers.retry import BackoffStrategy, CircuitBreakerState, RetryConfig

# ── ProviderError hierarchy ───────────────────────────────────────────────────


class TestProviderError:
    def test_base_error_message(self) -> None:
        err = ProviderError("something went wrong")
        assert str(err) == "something went wrong"

    def test_base_error_defaults(self) -> None:
        err = ProviderError("msg")
        assert err.provider_type is None
        assert err.retryable is False

    def test_base_error_with_provider_type(self) -> None:
        err = ProviderError("msg", provider_type="openai")
        assert err.provider_type == "openai"

    def test_base_error_retryable_flag(self) -> None:
        err = ProviderError("msg", retryable=True)
        assert err.retryable is True

    def test_rate_limit_is_retryable(self) -> None:
        err = RateLimitError()
        assert err.retryable is True

    def test_rate_limit_default_message(self) -> None:
        err = RateLimitError()
        assert "Rate limit" in str(err)

    def test_rate_limit_retry_after(self) -> None:
        err = RateLimitError(retry_after_seconds=30.5)
        assert err.retry_after_seconds == 30.5

    def test_rate_limit_retry_after_none_by_default(self) -> None:
        err = RateLimitError()
        assert err.retry_after_seconds is None

    def test_rate_limit_with_provider_type(self) -> None:
        err = RateLimitError(provider_type="anthropic")
        assert err.provider_type == "anthropic"

    def test_auth_error_not_retryable(self) -> None:
        err = AuthenticationError()
        assert err.retryable is False

    def test_auth_error_default_message(self) -> None:
        err = AuthenticationError()
        assert "Authentication" in str(err)

    def test_auth_error_custom_message(self) -> None:
        err = AuthenticationError("bad key", provider_type="openai")
        assert str(err) == "bad key"
        assert err.provider_type == "openai"

    def test_network_error_is_retryable(self) -> None:
        err = NetworkError()
        assert err.retryable is True

    def test_network_error_default_message(self) -> None:
        err = NetworkError()
        assert "Network" in str(err)

    def test_quota_exceeded_not_retryable(self) -> None:
        err = QuotaExceededError()
        assert err.retryable is False

    def test_quota_exceeded_default_message(self) -> None:
        err = QuotaExceededError()
        assert "Quota" in str(err)

    def test_invalid_request_not_retryable(self) -> None:
        err = InvalidRequestError()
        assert err.retryable is False

    def test_invalid_request_default_message(self) -> None:
        err = InvalidRequestError()
        assert "Invalid" in str(err)

    def test_internal_provider_error_retryable(self) -> None:
        err = InternalProviderError()
        assert err.retryable is True

    def test_internal_provider_error_default_message(self) -> None:
        err = InternalProviderError()
        assert "Internal" in str(err)

    def test_inheritance_chain(self) -> None:
        assert issubclass(RateLimitError, ProviderError)
        assert issubclass(AuthenticationError, ProviderError)
        assert issubclass(NetworkError, ProviderError)
        assert issubclass(QuotaExceededError, ProviderError)
        assert issubclass(InvalidRequestError, ProviderError)
        assert issubclass(InternalProviderError, ProviderError)

    def test_all_subclass_exception(self) -> None:
        assert issubclass(ProviderError, Exception)

    def test_catchable_as_provider_error(self) -> None:
        with pytest.raises(ProviderError):
            raise RateLimitError("too many requests")


# ── ProviderCapabilities ──────────────────────────────────────────────────────


class TestProviderCapabilities:
    def test_default_values(self) -> None:
        caps = ProviderCapabilities()
        assert caps.supports_streaming is False
        assert caps.supports_tool_calling is False
        assert caps.supports_vision is False
        assert caps.supports_audio is False
        assert caps.supports_usage_api is False
        assert caps.has_rate_limits is True
        assert caps.requires_api_key is True
        assert caps.supports_oauth is False
        assert caps.supports_fine_tuning is False
        assert caps.supports_function_calling is False
        assert caps.supports_web_sessions is False
        assert caps.max_context_window is None
        assert caps.supported_model_ids == frozenset()

    def test_custom_values(self) -> None:
        caps = ProviderCapabilities(
            supports_streaming=True,
            supports_tool_calling=True,
            max_context_window=128000,
            supported_model_ids=frozenset({"gpt-4o"}),
        )
        assert caps.supports_streaming is True
        assert caps.max_context_window == 128000
        assert "gpt-4o" in caps.supported_model_ids

    def test_frozen(self) -> None:
        caps = ProviderCapabilities()
        with pytest.raises((AttributeError, TypeError)):
            caps.supports_streaming = True  # type: ignore[misc]

    def test_equality(self) -> None:
        a = ProviderCapabilities(supports_streaming=True)
        b = ProviderCapabilities(supports_streaming=True)
        assert a == b

    def test_inequality(self) -> None:
        a = ProviderCapabilities(supports_streaming=True)
        b = ProviderCapabilities(supports_streaming=False)
        assert a != b


# ── Models ────────────────────────────────────────────────────────────────────


class TestModelCapabilityFlag:
    def test_values(self) -> None:
        assert ModelCapabilityFlag.STREAMING == "streaming"
        assert ModelCapabilityFlag.TOOL_CALLING == "tool_calling"
        assert ModelCapabilityFlag.VISION == "vision"
        assert ModelCapabilityFlag.AUDIO == "audio"
        assert ModelCapabilityFlag.FUNCTION_CALLING == "function_calling"
        assert ModelCapabilityFlag.FINE_TUNING == "fine_tuning"

    def test_is_str(self) -> None:
        assert isinstance(ModelCapabilityFlag.STREAMING, str)


class TestHealthStatus:
    def test_values(self) -> None:
        assert HealthStatus.HEALTHY == "healthy"
        assert HealthStatus.DEGRADED == "degraded"
        assert HealthStatus.UNHEALTHY == "unhealthy"
        assert HealthStatus.UNKNOWN == "unknown"

    def test_is_str(self) -> None:
        assert isinstance(HealthStatus.HEALTHY, str)


class TestUsageData:
    def test_defaults(self) -> None:
        u = UsageData()
        assert u.prompt_tokens == 0
        assert u.completion_tokens == 0
        assert u.total_tokens == 0
        assert u.cached_tokens is None

    def test_frozen(self) -> None:
        u = UsageData(prompt_tokens=10)
        with pytest.raises((AttributeError, TypeError, ValueError)):
            u.prompt_tokens = 20  # type: ignore[misc]

    def test_with_values(self) -> None:
        u = UsageData(prompt_tokens=100, completion_tokens=50, total_tokens=150, cached_tokens=20)
        assert u.total_tokens == 150
        assert u.cached_tokens == 20


class TestModelMetadata:
    def test_basic(self) -> None:
        m = ModelMetadata(id="gpt-4o", display_name="GPT-4o", provider_type="openai")
        assert m.id == "gpt-4o"
        assert m.display_name == "GPT-4o"
        assert m.provider_type == "openai"

    def test_defaults(self) -> None:
        m = ModelMetadata(id="x", display_name="X", provider_type="openai")
        assert m.context_window is None
        assert m.max_output_tokens is None
        assert m.capabilities == frozenset()
        assert m.is_deprecated is False
        assert m.deprecated_at is None
        assert m.input_cost_per_1k is None
        assert m.output_cost_per_1k is None

    def test_with_capabilities(self) -> None:
        caps = frozenset({ModelCapabilityFlag.STREAMING, ModelCapabilityFlag.VISION})
        m = ModelMetadata(id="x", display_name="X", provider_type="openai", capabilities=caps)
        assert ModelCapabilityFlag.STREAMING in m.capabilities
        assert ModelCapabilityFlag.VISION in m.capabilities

    def test_deprecated(self) -> None:
        m = ModelMetadata(id="old", display_name="Old", provider_type="openai", is_deprecated=True)
        assert m.is_deprecated is True

    def test_frozen(self) -> None:
        m = ModelMetadata(id="x", display_name="X", provider_type="openai")
        with pytest.raises((AttributeError, TypeError, ValueError)):
            m.id = "y"  # type: ignore[misc]


class TestConnectionStatus:
    def test_basic(self) -> None:
        from datetime import datetime

        cs = ConnectionStatus(
            is_connected=True,
            health_status=HealthStatus.HEALTHY,
            checked_at=datetime.now(UTC),
        )
        assert cs.is_connected is True
        assert cs.health_status == HealthStatus.HEALTHY

    def test_with_error(self) -> None:
        from datetime import datetime

        cs = ConnectionStatus(
            is_connected=False,
            health_status=HealthStatus.UNHEALTHY,
            error_message="timeout",
            checked_at=datetime.now(UTC),
        )
        assert cs.error_message == "timeout"
        assert cs.latency_ms is None


class TestProviderRequest:
    def test_basic(self) -> None:
        req = ProviderRequest(
            model_id="gpt-4o",
            messages=[{"role": "user", "content": "hello"}],
        )
        assert req.model_id == "gpt-4o"
        assert req.stream is False
        assert req.extra == {}

    def test_with_options(self) -> None:
        req = ProviderRequest(
            model_id="gpt-4o",
            messages=[],
            max_tokens=1000,
            temperature=0.7,
            stream=True,
        )
        assert req.max_tokens == 1000
        assert req.temperature == 0.7
        assert req.stream is True


class TestProviderResponse:
    def test_basic(self) -> None:
        resp = ProviderResponse(model_id="gpt-4o", content="hello world")
        assert resp.model_id == "gpt-4o"
        assert resp.content == "hello world"
        assert resp.usage is None
        assert resp.finish_reason is None
        assert resp.raw_response == {}

    def test_with_usage(self) -> None:
        usage = UsageData(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        resp = ProviderResponse(
            model_id="gpt-4o",
            content="hi",
            usage=usage,
            finish_reason="stop",
        )
        assert resp.usage is not None
        assert resp.usage.total_tokens == 15
        assert resp.finish_reason == "stop"

    def test_frozen(self) -> None:
        resp = ProviderResponse(model_id="gpt-4o", content="hi")
        with pytest.raises((AttributeError, TypeError, ValueError)):
            resp.content = "bye"  # type: ignore[misc]


# ── Config models ─────────────────────────────────────────────────────────────


class TestSecretReference:
    def test_basic(self) -> None:
        ref = SecretReference(secret_key="OPENAI_API_KEY")
        assert ref.secret_store == "env"
        assert ref.secret_key == "OPENAI_API_KEY"

    def test_custom_store(self) -> None:
        ref = SecretReference(secret_store="vault", secret_key="my-secret")
        assert ref.secret_store == "vault"

    def test_repr_redacts_key(self) -> None:
        ref = SecretReference(secret_key="supersecret")
        r = repr(ref)
        assert "supersecret" not in r
        assert "<redacted>" in r

    def test_frozen(self) -> None:
        ref = SecretReference(secret_key="key")
        with pytest.raises((AttributeError, TypeError, ValueError)):
            ref.secret_key = "newkey"  # type: ignore[misc]


class TestProviderConfig:
    def test_basic(self) -> None:
        cfg = ProviderConfig(provider_type="openai", display_name="OpenAI")
        assert cfg.provider_type == "openai"
        assert cfg.timeout_seconds == 30.0
        assert cfg.config_version == 1
        assert cfg.extra == {}

    def test_rejects_plaintext_api_key(self) -> None:
        with pytest.raises(ValueError, match="SecretReference"):
            ProviderConfig(
                provider_type="openai",
                display_name="OpenAI",
                extra={"api_key": "sk-secret"},
            )

    def test_rejects_plaintext_password(self) -> None:
        with pytest.raises(ValueError, match="SecretReference"):
            ProviderConfig(
                provider_type="openai",
                display_name="OpenAI",
                extra={"password": "hunter2"},
            )

    def test_rejects_plaintext_token(self) -> None:
        with pytest.raises(ValueError, match="SecretReference"):
            ProviderConfig(
                provider_type="openai",
                display_name="OpenAI",
                extra={"auth_token": "abc123"},
            )

    def test_allows_non_sensitive_extra(self) -> None:
        cfg = ProviderConfig(
            provider_type="openai",
            display_name="OpenAI",
            extra={"model_alias": "my-gpt4"},
        )
        assert cfg.extra["model_alias"] == "my-gpt4"

    def test_with_secret_reference(self) -> None:
        ref = SecretReference(secret_key="OPENAI_API_KEY")
        cfg = ProviderConfig(
            provider_type="openai",
            display_name="OpenAI",
            api_key_ref=ref,
        )
        assert cfg.api_key_ref is not None
        assert cfg.api_key_ref.secret_key == "OPENAI_API_KEY"


class TestOpenAIConfig:
    def test_defaults(self) -> None:
        cfg = OpenAIConfig(display_name="OpenAI")
        assert cfg.provider_type == "openai"
        assert cfg.organization_id is None
        assert cfg.project_id is None

    def test_with_org(self) -> None:
        cfg = OpenAIConfig(display_name="OpenAI", organization_id="org-123")
        assert cfg.organization_id == "org-123"


class TestAnthropicConfig:
    def test_defaults(self) -> None:
        cfg = AnthropicConfig(display_name="Anthropic")
        assert cfg.provider_type == "anthropic"
        assert cfg.anthropic_version == "2023-06-01"


class TestGrokConfig:
    def test_defaults(self) -> None:
        cfg = GrokConfig(display_name="Grok")
        assert cfg.provider_type == "grok"
        assert cfg.base_url == "https://api.x.ai/v1"


class TestGoogleConfig:
    def test_defaults(self) -> None:
        cfg = GoogleConfig(display_name="Google")
        assert cfg.provider_type == "google"
        assert cfg.location == "us-central1"
        assert cfg.project_id is None


class TestAzureOpenAIConfig:
    def test_required_endpoint(self) -> None:
        cfg = AzureOpenAIConfig(
            display_name="Azure",
            azure_endpoint="https://myaccount.openai.azure.com",
        )
        assert cfg.azure_endpoint == "https://myaccount.openai.azure.com"
        assert cfg.api_version == "2024-02-01"

    def test_missing_endpoint_fails(self) -> None:
        with pytest.raises((TypeError, ValueError)):
            AzureOpenAIConfig(display_name="Azure")  # type: ignore[call-arg]


class TestOpenRouterConfig:
    def test_defaults(self) -> None:
        cfg = OpenRouterConfig(display_name="OpenRouter")
        assert cfg.provider_type == "openrouter"
        assert cfg.base_url == "https://openrouter.ai/api/v1"
        assert cfg.http_referer is None
        assert cfg.x_title is None


class TestOllamaConfig:
    def test_defaults(self) -> None:
        cfg = OllamaConfig(display_name="Ollama")
        assert cfg.provider_type == "ollama"
        assert cfg.base_url == "http://localhost:11434"
        assert cfg.requires_api_key is False


# ── ProviderRegistry ──────────────────────────────────────────────────────────


class TestProviderRegistry:
    def _make_registry(self) -> ProviderRegistry:
        return ProviderRegistry()

    def test_empty_registry(self) -> None:
        reg = self._make_registry()
        assert len(reg) == 0

    def test_register_and_get(self) -> None:
        reg = self._make_registry()
        reg.register(ProviderType.OPENAI, OpenAIProvider)
        cls = reg.get(ProviderType.OPENAI)
        assert cls is OpenAIProvider

    def test_is_registered_true(self) -> None:
        reg = self._make_registry()
        reg.register(ProviderType.OPENAI, OpenAIProvider)
        assert reg.is_registered(ProviderType.OPENAI) is True

    def test_is_registered_false(self) -> None:
        reg = self._make_registry()
        assert reg.is_registered(ProviderType.OPENAI) is False

    def test_get_unregistered_raises(self) -> None:
        reg = self._make_registry()
        with pytest.raises(KeyError, match="openai"):
            reg.get(ProviderType.OPENAI)

    def test_registered_types(self) -> None:
        reg = self._make_registry()
        reg.register(ProviderType.OPENAI, OpenAIProvider)
        reg.register(ProviderType.ANTHROPIC, AnthropicProvider)
        types = reg.registered_types()
        assert ProviderType.OPENAI in types
        assert ProviderType.ANTHROPIC in types

    def test_len(self) -> None:
        reg = self._make_registry()
        reg.register(ProviderType.OPENAI, OpenAIProvider)
        assert len(reg) == 1
        reg.register(ProviderType.ANTHROPIC, AnthropicProvider)
        assert len(reg) == 2

    def test_overwrite_registration(self) -> None:
        reg = self._make_registry()
        reg.register(ProviderType.OPENAI, OpenAIProvider)
        reg.register(ProviderType.OPENAI, AnthropicProvider)
        assert reg.get(ProviderType.OPENAI) is AnthropicProvider

    def test_all_registered_types_listed(self) -> None:
        reg = ProviderFactory.build_default_registry()
        types = reg.registered_types()
        assert len(types) == 7
        for pt in ProviderType:
            assert pt in types


# ── ProviderFactory ───────────────────────────────────────────────────────────


class TestProviderFactory:
    def _make_factory(self) -> ProviderFactory:
        registry = ProviderFactory.build_default_registry()
        return ProviderFactory(registry)

    def test_create_openai(self) -> None:
        factory = self._make_factory()
        cfg = OpenAIConfig(display_name="OpenAI")
        provider = factory.create(cfg)
        assert isinstance(provider, OpenAIProvider)

    def test_create_anthropic(self) -> None:
        factory = self._make_factory()
        cfg = AnthropicConfig(display_name="Anthropic")
        provider = factory.create(cfg)
        assert isinstance(provider, AnthropicProvider)

    def test_create_grok(self) -> None:
        factory = self._make_factory()
        cfg = GrokConfig(display_name="Grok")
        provider = factory.create(cfg)
        assert isinstance(provider, GrokProvider)

    def test_create_google(self) -> None:
        factory = self._make_factory()
        cfg = GoogleConfig(display_name="Google")
        provider = factory.create(cfg)
        assert isinstance(provider, GoogleProvider)

    def test_create_azure_openai(self) -> None:
        factory = self._make_factory()
        cfg = AzureOpenAIConfig(
            display_name="Azure", azure_endpoint="https://myaccount.openai.azure.com"
        )
        provider = factory.create(cfg)
        assert isinstance(provider, AzureOpenAIProvider)

    def test_create_openrouter(self) -> None:
        factory = self._make_factory()
        cfg = OpenRouterConfig(display_name="OpenRouter")
        provider = factory.create(cfg)
        assert isinstance(provider, OpenRouterProvider)

    def test_create_ollama(self) -> None:
        factory = self._make_factory()
        cfg = OllamaConfig(display_name="Ollama")
        provider = factory.create(cfg)
        assert isinstance(provider, OllamaProvider)

    def test_create_invalid_type_raises(self) -> None:
        factory = self._make_factory()
        cfg = ProviderConfig(provider_type="nonexistent_provider", display_name="X")
        with pytest.raises((KeyError, ValueError)):
            factory.create(cfg)

    def test_build_default_registry_has_all_providers(self) -> None:
        registry = ProviderFactory.build_default_registry()
        assert len(registry) == 7

    def test_provider_config_is_accessible(self) -> None:
        factory = self._make_factory()
        cfg = OpenAIConfig(display_name="My OpenAI")
        provider = factory.create(cfg)
        assert provider.config is cfg
        assert provider.display_name == "My OpenAI"


# ── Adapter stubs — OpenAI ────────────────────────────────────────────────────


class TestOpenAIProvider:
    def _make(self) -> OpenAIProvider:
        cfg = OpenAIConfig(display_name="OpenAI Test")
        return OpenAIProvider(cfg)

    def test_provider_type(self) -> None:
        p = self._make()
        assert p.provider_type == ProviderType.OPENAI

    def test_capabilities(self) -> None:
        p = self._make()
        assert p.capabilities.supports_streaming is True
        assert p.capabilities.supports_vision is True
        assert p.capabilities.supports_fine_tuning is True

    @pytest.mark.asyncio
    async def test_check_connection_returns_unknown(self) -> None:
        p = self._make()
        status = await p.check_connection()
        assert status.health_status == HealthStatus.UNKNOWN
        assert status.is_connected is False

    @pytest.mark.asyncio
    async def test_list_models(self) -> None:
        p = self._make()
        models = await p.list_models()
        assert len(models) > 0
        ids = [m.id for m in models]
        assert "gpt-4o" in ids

    @pytest.mark.asyncio
    async def test_complete_raises_not_implemented(self) -> None:
        p = self._make()
        req = ProviderRequest(model_id="gpt-4o", messages=[])
        with pytest.raises(NotImplementedError):
            await p.complete(req)

    @pytest.mark.asyncio
    async def test_verify_auth_raises_not_implemented(self) -> None:
        p = self._make()
        with pytest.raises(NotImplementedError):
            await p.verify_auth()

    def test_isinstance_ai_provider(self) -> None:
        p = self._make()
        assert isinstance(p, AIProvider)

    @pytest.mark.asyncio
    async def test_deprecated_model_in_list(self) -> None:
        p = self._make()
        models = await p.list_models()
        deprecated = [m for m in models if m.is_deprecated]
        assert any(m.id == "gpt-3.5-turbo" for m in deprecated)


# ── Adapter stubs — Anthropic ─────────────────────────────────────────────────


class TestAnthropicProvider:
    def _make(self) -> AnthropicProvider:
        cfg = AnthropicConfig(display_name="Anthropic Test")
        return AnthropicProvider(cfg)

    def test_provider_type(self) -> None:
        p = self._make()
        assert p.provider_type == ProviderType.ANTHROPIC

    def test_capabilities(self) -> None:
        p = self._make()
        assert p.capabilities.supports_streaming is True
        assert p.capabilities.supports_fine_tuning is False
        assert p.capabilities.max_context_window == 200000

    @pytest.mark.asyncio
    async def test_check_connection(self) -> None:
        p = self._make()
        status = await p.check_connection()
        assert status.health_status == HealthStatus.UNKNOWN

    @pytest.mark.asyncio
    async def test_list_models(self) -> None:
        p = self._make()
        models = await p.list_models()
        ids = [m.id for m in models]
        assert any("claude" in mid for mid in ids)

    @pytest.mark.asyncio
    async def test_complete_not_implemented(self) -> None:
        p = self._make()
        with pytest.raises(NotImplementedError):
            await p.complete(ProviderRequest(model_id="claude-3-5-sonnet-20241022", messages=[]))

    @pytest.mark.asyncio
    async def test_verify_auth_not_implemented(self) -> None:
        p = self._make()
        with pytest.raises(NotImplementedError):
            await p.verify_auth()


# ── Adapter stubs — Grok ─────────────────────────────────────────────────────


class TestGrokProvider:
    def _make(self) -> GrokProvider:
        cfg = GrokConfig(display_name="Grok Test")
        return GrokProvider(cfg)

    def test_provider_type(self) -> None:
        assert self._make().provider_type == ProviderType.GROK

    @pytest.mark.asyncio
    async def test_list_models(self) -> None:
        models = await self._make().list_models()
        assert len(models) >= 1
        ids = [m.id for m in models]
        assert any("grok" in mid for mid in ids)

    @pytest.mark.asyncio
    async def test_complete_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError):
            await self._make().complete(ProviderRequest(model_id="grok-2-1212", messages=[]))

    @pytest.mark.asyncio
    async def test_verify_auth_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError):
            await self._make().verify_auth()


# ── Adapter stubs — Google ────────────────────────────────────────────────────


class TestGoogleProvider:
    def _make(self) -> GoogleProvider:
        cfg = GoogleConfig(display_name="Google Test")
        return GoogleProvider(cfg)

    def test_provider_type(self) -> None:
        assert self._make().provider_type == ProviderType.GOOGLE

    def test_capabilities_oauth(self) -> None:
        assert self._make().capabilities.supports_oauth is True

    @pytest.mark.asyncio
    async def test_list_models(self) -> None:
        models = await self._make().list_models()
        ids = [m.id for m in models]
        assert any("gemini" in mid for mid in ids)

    @pytest.mark.asyncio
    async def test_complete_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError):
            await self._make().complete(ProviderRequest(model_id="gemini-1.5-pro", messages=[]))

    @pytest.mark.asyncio
    async def test_verify_auth_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError):
            await self._make().verify_auth()


# ── Adapter stubs — AzureOpenAI ──────────────────────────────────────────────


class TestAzureOpenAIProvider:
    def _make(self) -> AzureOpenAIProvider:
        cfg = AzureOpenAIConfig(
            display_name="Azure Test",
            azure_endpoint="https://test.openai.azure.com",
        )
        return AzureOpenAIProvider(cfg)

    def test_provider_type(self) -> None:
        assert self._make().provider_type == ProviderType.AZURE_OPENAI

    def test_capabilities_oauth(self) -> None:
        assert self._make().capabilities.supports_oauth is True

    @pytest.mark.asyncio
    async def test_list_models(self) -> None:
        models = await self._make().list_models()
        assert len(models) >= 1

    @pytest.mark.asyncio
    async def test_complete_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError):
            await self._make().complete(ProviderRequest(model_id="gpt-4o", messages=[]))

    @pytest.mark.asyncio
    async def test_verify_auth_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError):
            await self._make().verify_auth()


# ── Adapter stubs — OpenRouter ────────────────────────────────────────────────


class TestOpenRouterProvider:
    def _make(self) -> OpenRouterProvider:
        cfg = OpenRouterConfig(display_name="OpenRouter Test")
        return OpenRouterProvider(cfg)

    def test_provider_type(self) -> None:
        assert self._make().provider_type == ProviderType.OPENROUTER

    def test_capabilities_no_fine_tuning(self) -> None:
        assert self._make().capabilities.supports_fine_tuning is False

    @pytest.mark.asyncio
    async def test_list_models(self) -> None:
        models = await self._make().list_models()
        assert len(models) >= 1

    @pytest.mark.asyncio
    async def test_complete_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError):
            await self._make().complete(ProviderRequest(model_id="openai/gpt-4o", messages=[]))

    @pytest.mark.asyncio
    async def test_verify_auth_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError):
            await self._make().verify_auth()


# ── Adapter stubs — Ollama ────────────────────────────────────────────────────


class TestOllamaProvider:
    def _make(self) -> OllamaProvider:
        cfg = OllamaConfig(display_name="Ollama Test")
        return OllamaProvider(cfg)

    def test_provider_type(self) -> None:
        assert self._make().provider_type == ProviderType.OLLAMA

    def test_capabilities_no_api_key(self) -> None:
        caps = self._make().capabilities
        assert caps.requires_api_key is False
        assert caps.has_rate_limits is False
        assert caps.supports_usage_api is False

    @pytest.mark.asyncio
    async def test_list_models(self) -> None:
        models = await self._make().list_models()
        assert len(models) >= 1
        ids = [m.id for m in models]
        assert any(mid in ("llama3.2", "llama3.1", "mistral") for mid in ids)

    @pytest.mark.asyncio
    async def test_complete_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError):
            await self._make().complete(ProviderRequest(model_id="llama3.2", messages=[]))

    @pytest.mark.asyncio
    async def test_verify_auth_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError):
            await self._make().verify_auth()


# ── Retry models ──────────────────────────────────────────────────────────────


class TestRetryConfig:
    def test_defaults(self) -> None:
        cfg = RetryConfig()
        assert cfg.max_attempts == 3
        assert cfg.initial_delay_seconds == 1.0
        assert cfg.max_delay_seconds == 60.0
        assert cfg.backoff_strategy == BackoffStrategy.EXPONENTIAL
        assert cfg.backoff_multiplier == 2.0
        assert cfg.retryable_error_types == frozenset()

    def test_custom(self) -> None:
        cfg = RetryConfig(max_attempts=5, backoff_strategy=BackoffStrategy.FIXED)
        assert cfg.max_attempts == 5
        assert cfg.backoff_strategy == BackoffStrategy.FIXED

    def test_frozen(self) -> None:
        cfg = RetryConfig()
        with pytest.raises((AttributeError, TypeError)):
            cfg.max_attempts = 10  # type: ignore[misc]


class TestBackoffStrategy:
    def test_values(self) -> None:
        assert BackoffStrategy.FIXED == "fixed"
        assert BackoffStrategy.LINEAR == "linear"
        assert BackoffStrategy.EXPONENTIAL == "exponential"
        assert BackoffStrategy.JITTER == "jitter"

    def test_is_str(self) -> None:
        assert isinstance(BackoffStrategy.EXPONENTIAL, str)


class TestCircuitBreakerState:
    def test_values(self) -> None:
        assert CircuitBreakerState.CLOSED == "closed"
        assert CircuitBreakerState.OPEN == "open"
        assert CircuitBreakerState.HALF_OPEN == "half_open"


# ── get_registry singleton ────────────────────────────────────────────────────


class TestGetRegistry:
    def test_get_registry_returns_registry(self) -> None:
        from app.providers.registry import get_registry

        reg = get_registry()
        assert isinstance(reg, ProviderRegistry)
        assert len(reg) == 7

    def test_get_registry_is_singleton(self) -> None:
        from app.providers.registry import get_registry

        reg1 = get_registry()
        reg2 = get_registry()
        assert reg1 is reg2


# ── __init__.py public exports ─────────────────────────────────────────────────


class TestPublicExports:
    def test_all_exports_importable(self) -> None:
        from app.providers import (
            AIProvider,
            AuthenticationError,
            InternalProviderError,
            InvalidRequestError,
            NetworkError,
            ProviderCapabilities,
            ProviderError,
            ProviderFactory,
            ProviderRegistry,
            QuotaExceededError,
            RateLimitError,
        )

        assert AIProvider is not None
        assert ProviderRegistry is not None
        assert ProviderFactory is not None
        assert ProviderCapabilities is not None
        assert ProviderError is not None
        assert RateLimitError is not None
        assert AuthenticationError is not None
        assert NetworkError is not None
        assert QuotaExceededError is not None
        assert InvalidRequestError is not None
        assert InternalProviderError is not None
