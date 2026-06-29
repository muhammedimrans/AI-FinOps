"""EP-07 test suite — OpenAI & Anthropic provider integration.

Coverage targets:
- F-033: HTTP transport, auth strategies, telemetry, retry policy
- F-034: OpenAI adapter (verify_auth, check_connection, is_healthy, list_models,
         check_capability, get_provider_info)
- F-035: Anthropic adapter (same methods)
- F-036: Credential validation and secret resolution
- F-037: Health checking (ConnectionStatus, HealthStatus)
- F-038: Model discovery (live mock + static enrichment)
- F-039: Error mapping (HTTP status codes → ProviderError subclasses)
- F-040: ProviderInfo model

All tests are hermetic — no network calls.  Provider adapters receive a
mock httpx transport so real API calls are never made.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from unittest.mock import MagicMock

import httpx
import pytest

from app.http.auth import ApiKeyHeaderAuth, BearerTokenAuth, CompositeAuth
from app.http.client import ProviderHttpClient, map_http_error
from app.http.retry import ExponentialRetryPolicy
from app.http.telemetry import RequestTelemetry
from app.http.transport import HttpxTransport
from app.providers.capabilities import ProviderCapabilities
from app.providers.config import (
    AnthropicConfig,
    OpenAIConfig,
    SecretReference,
    SecretStoreType,
)
from app.providers.credential import CredentialValidator, SecretResolver
from app.providers.errors import (
    AuthenticationError,
    InternalProviderError,
    InvalidRequestError,
    NetworkError,
    ProviderError,
    RateLimitError,
)
from app.providers.info import ProviderInfo
from app.providers.models import (
    ConnectionStatus,
    HealthStatus,
    ModelCapabilityFlag,
    ModelMetadata,
)
from app.providers.retry import BackoffStrategy, RetryConfig

# ── Test helpers ──────────────────────────────────────────────────────────────


def _no_retry_policy() -> ExponentialRetryPolicy:
    """Return a retry policy that never retries (max_attempts=1)."""
    return ExponentialRetryPolicy(RetryConfig(max_attempts=1))


# ── Helpers ───────────────────────────────────────────────────────────────────

_VALID_OPENAI_KEY = "sk-" + "a" * 30
_VALID_ANTHROPIC_KEY = "sk-ant-" + "b" * 30


def _make_response(
    status_code: int,
    body: object = None,
    headers: dict[str, str] | None = None,
    url: str = "https://api.openai.com/v1/models",
) -> httpx.Response:
    content = json.dumps(body or {}).encode()
    resp = httpx.Response(status_code, content=content, headers=headers or {})
    # Attach a synthetic request so response.url works in error-mapping code.
    resp.request = httpx.Request("GET", url)
    return resp


def _mock_transport(responses: list[httpx.Response]) -> httpx.MockTransport:
    """Return a MockTransport that yields each response in order."""
    responses_iter = iter(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        return next(responses_iter)

    return httpx.MockTransport(handler=handler)


def _openai_config(*, key: str = _VALID_OPENAI_KEY) -> OpenAIConfig:
    return OpenAIConfig(
        provider_type="openai",
        display_name="OpenAI",
        api_key_ref=SecretReference(secret_store=SecretStoreType.ENV, secret_key="TEST_OAI_KEY"),
    )


def _anthropic_config(*, key: str = _VALID_ANTHROPIC_KEY) -> AnthropicConfig:
    return AnthropicConfig(
        provider_type="anthropic",
        display_name="Anthropic",
        api_key_ref=SecretReference(
            secret_store=SecretStoreType.ENV, secret_key="TEST_ANT_KEY"
        ),
    )


# ── F-033: HTTP auth strategies ───────────────────────────────────────────────


class TestBearerTokenAuth:
    def test_headers_contain_bearer(self) -> None:
        auth = BearerTokenAuth("my-token")
        assert auth.headers() == {"Authorization": "Bearer my-token"}

    def test_headers_are_new_dict_each_call(self) -> None:
        auth = BearerTokenAuth("tok")
        h1 = auth.headers()
        h2 = auth.headers()
        assert h1 is not h2

    def test_token_not_repr(self) -> None:
        auth = BearerTokenAuth("secret")
        assert "secret" not in repr(auth)


class TestApiKeyHeaderAuth:
    def test_custom_header(self) -> None:
        auth = ApiKeyHeaderAuth("x-api-key", "my-key")
        assert auth.headers() == {"x-api-key": "my-key"}

    def test_anthropic_version_header(self) -> None:
        auth = ApiKeyHeaderAuth("anthropic-version", "2023-06-01")
        assert auth.headers() == {"anthropic-version": "2023-06-01"}


class TestCompositeAuth:
    def test_merges_headers(self) -> None:
        auth = CompositeAuth(
            BearerTokenAuth("tok"),
            ApiKeyHeaderAuth("x-custom", "val"),
        )
        h = auth.headers()
        assert h["Authorization"] == "Bearer tok"
        assert h["x-custom"] == "val"

    def test_last_write_wins(self) -> None:
        auth = CompositeAuth(
            ApiKeyHeaderAuth("x-key", "first"),
            ApiKeyHeaderAuth("x-key", "second"),
        )
        assert auth.headers()["x-key"] == "second"

    def test_empty_composite(self) -> None:
        auth = CompositeAuth()
        assert auth.headers() == {}


# ── F-039: HTTP error mapping ─────────────────────────────────────────────────


class TestMapHttpError:
    def _resp(self, code: int, retry_after: str | None = None) -> httpx.Response:
        headers = {"Retry-After": retry_after} if retry_after else {}
        return _make_response(code, headers=headers)

    def test_401_is_auth_error(self) -> None:
        err = map_http_error(self._resp(401), provider_type="openai")
        assert isinstance(err, AuthenticationError)

    def test_403_is_auth_error(self) -> None:
        err = map_http_error(self._resp(403), provider_type="openai")
        assert isinstance(err, AuthenticationError)

    def test_404_is_invalid_request(self) -> None:
        err = map_http_error(self._resp(404), provider_type="openai")
        assert isinstance(err, InvalidRequestError)

    def test_408_is_network_error(self) -> None:
        err = map_http_error(self._resp(408), provider_type="openai")
        assert isinstance(err, NetworkError)

    def test_504_is_network_error(self) -> None:
        err = map_http_error(self._resp(504), provider_type="openai")
        assert isinstance(err, NetworkError)

    def test_429_is_rate_limit_error(self) -> None:
        err = map_http_error(self._resp(429), provider_type="openai")
        assert isinstance(err, RateLimitError)

    def test_429_parses_retry_after(self) -> None:
        err = map_http_error(self._resp(429, retry_after="30"), provider_type="openai")
        assert isinstance(err, RateLimitError)
        assert err.retry_after_seconds == 30.0

    def test_429_bad_retry_after_is_none(self) -> None:
        err = map_http_error(self._resp(429, retry_after="soon"), provider_type="openai")
        assert isinstance(err, RateLimitError)
        assert err.retry_after_seconds is None

    def test_500_is_internal_error(self) -> None:
        err = map_http_error(self._resp(500), provider_type="openai")
        assert isinstance(err, InternalProviderError)

    def test_502_is_internal_error(self) -> None:
        err = map_http_error(self._resp(502), provider_type="openai")
        assert isinstance(err, InternalProviderError)

    def test_503_is_internal_error(self) -> None:
        err = map_http_error(self._resp(503), provider_type="openai")
        assert isinstance(err, InternalProviderError)

    def test_unknown_status_is_provider_error(self) -> None:
        err = map_http_error(self._resp(418), provider_type="openai")
        assert isinstance(err, ProviderError)
        assert "418" in str(err)

    def test_provider_type_attached(self) -> None:
        err = map_http_error(self._resp(401), provider_type="anthropic")
        assert err.provider_type == "anthropic"

    def test_error_not_retryable_on_401(self) -> None:
        err = map_http_error(self._resp(401), provider_type="openai")
        assert not err.retryable

    def test_error_retryable_on_429(self) -> None:
        err = map_http_error(self._resp(429), provider_type="openai")
        assert err.retryable

    def test_error_retryable_on_503(self) -> None:
        err = map_http_error(self._resp(503), provider_type="openai")
        assert err.retryable


# ── F-033: ProviderHttpClient ─────────────────────────────────────────────────


class TestProviderHttpClient:
    @pytest.mark.asyncio
    async def test_get_success(self) -> None:
        transport = _mock_transport([_make_response(200, {"ok": True})])
        auth = BearerTokenAuth(_VALID_OPENAI_KEY)
        async with ProviderHttpClient(
            base_url="https://api.openai.com",
            auth=auth,
            provider_type="openai",
            mock_transport=transport,
        ) as client:
            data = await client.get("/v1/models")
        assert data == {"ok": True}

    @pytest.mark.asyncio
    async def test_get_adds_request_id_header(self) -> None:
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return _make_response(200, {})

        transport = httpx.MockTransport(handler=handler)
        auth = BearerTokenAuth("sk-test")
        async with ProviderHttpClient(
            base_url="https://api.openai.com",
            auth=auth,
            provider_type="openai",
            mock_transport=transport,
        ) as client:
            await client.get("/v1/test")

        assert "x-request-id" in captured[0].headers

    @pytest.mark.asyncio
    async def test_get_adds_user_agent(self) -> None:
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return _make_response(200, {})

        async with ProviderHttpClient(
            base_url="https://api.openai.com",
            auth=BearerTokenAuth("sk-test"),
            provider_type="openai",
            mock_transport=httpx.MockTransport(handler=handler),
        ) as client:
            await client.get("/v1/test")

        assert "user-agent" in captured[0].headers

    @pytest.mark.asyncio
    async def test_get_raises_on_401(self) -> None:
        transport = _mock_transport([_make_response(401)])
        async with ProviderHttpClient(
            base_url="https://api.openai.com",
            auth=BearerTokenAuth("sk-bad"),
            provider_type="openai",
            mock_transport=transport,
        ) as client:
            with pytest.raises(AuthenticationError):
                await client.get("/v1/models")

    @pytest.mark.asyncio
    async def test_get_raises_on_429(self) -> None:
        transport = _mock_transport([_make_response(429)])
        async with ProviderHttpClient(
            base_url="https://api.openai.com",
            auth=BearerTokenAuth("sk-test"),
            provider_type="openai",
            mock_transport=transport,
            retry_policy=_no_retry_policy(),
        ) as client:
            with pytest.raises(RateLimitError):
                await client.get("/v1/models")

    @pytest.mark.asyncio
    async def test_non_json_response_raises_internal_error(self) -> None:
        response = httpx.Response(200, content=b"not-json")
        transport = _mock_transport([response])
        async with ProviderHttpClient(
            base_url="https://api.openai.com",
            auth=BearerTokenAuth("sk-test"),
            provider_type="openai",
            mock_transport=transport,
        ) as client:
            with pytest.raises(InternalProviderError):
                await client.get("/v1/test")

    @pytest.mark.asyncio
    async def test_timeout_raises_network_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("timeout", request=request)

        async with ProviderHttpClient(
            base_url="https://api.openai.com",
            auth=BearerTokenAuth("sk-test"),
            provider_type="openai",
            mock_transport=httpx.MockTransport(handler=handler),
            retry_policy=_no_retry_policy(),
        ) as client:
            with pytest.raises(NetworkError):
                await client.get("/v1/test")

    @pytest.mark.asyncio
    async def test_connect_error_raises_network_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("DNS failure", request=request)

        async with ProviderHttpClient(
            base_url="https://api.openai.com",
            auth=BearerTokenAuth("sk-test"),
            provider_type="openai",
            mock_transport=httpx.MockTransport(handler=handler),
            retry_policy=_no_retry_policy(),
        ) as client:
            with pytest.raises(NetworkError):
                await client.get("/v1/test")


# ── F-033: RequestTelemetry ───────────────────────────────────────────────────


class TestRequestTelemetry:
    def test_latency_is_measured(self) -> None:
        tel = RequestTelemetry(method="GET", url="https://x.com", provider="openai")
        with tel:
            pass
        assert tel.latency_ms >= 0

    def test_error_is_set_on_exception(self) -> None:
        tel = RequestTelemetry(method="GET", url="https://x.com", provider="openai")
        try:
            with tel:
                raise ValueError("boom")
        except ValueError:
            pass
        assert tel.error == "ValueError"

    def test_no_error_when_clean(self) -> None:
        tel = RequestTelemetry(method="GET", url="https://x.com", provider="openai")
        with tel:
            tel.status_code = 200
        assert tel.error is None
        assert tel.status_code == 200

    def test_request_id_is_uuid(self) -> None:
        import uuid

        tel = RequestTelemetry(method="GET", url="https://x.com", provider="openai")
        parsed = uuid.UUID(tel.request_id)
        assert parsed.version == 4


# ── F-033: ExponentialRetryPolicy ────────────────────────────────────────────


class TestExponentialRetryPolicy:
    def test_should_not_retry_auth_error(self) -> None:
        policy = ExponentialRetryPolicy()
        err = AuthenticationError("bad key", provider_type="openai")
        assert not policy.should_retry(1, err)

    def test_should_not_retry_invalid_request(self) -> None:
        policy = ExponentialRetryPolicy()
        err = InvalidRequestError("bad param", provider_type="openai")
        assert not policy.should_retry(1, err)

    def test_should_retry_rate_limit(self) -> None:
        policy = ExponentialRetryPolicy()
        err = RateLimitError("too fast", provider_type="openai")
        assert policy.should_retry(1, err)

    def test_should_retry_network_error(self) -> None:
        policy = ExponentialRetryPolicy()
        err = NetworkError("timeout", provider_type="openai")
        assert policy.should_retry(1, err)

    def test_should_retry_internal_error(self) -> None:
        policy = ExponentialRetryPolicy()
        err = InternalProviderError("server error", provider_type="openai")
        assert policy.should_retry(1, err)

    def test_max_attempts_stops_retry(self) -> None:
        cfg = RetryConfig(max_attempts=2)
        policy = ExponentialRetryPolicy(cfg)
        err = NetworkError("timeout", provider_type="openai")
        assert policy.should_retry(1, err)
        assert not policy.should_retry(2, err)

    def test_exponential_delay_increases(self) -> None:
        policy = ExponentialRetryPolicy(RetryConfig(initial_delay_seconds=1.0, backoff_multiplier=2.0))
        d1 = policy.get_delay(1)
        d2 = policy.get_delay(2)
        assert d2 > d1

    def test_delay_capped_at_max(self) -> None:
        cfg = RetryConfig(initial_delay_seconds=100.0, max_delay_seconds=5.0)
        policy = ExponentialRetryPolicy(cfg)
        assert policy.get_delay(1) == 5.0

    def test_fixed_backoff(self) -> None:
        cfg = RetryConfig(backoff_strategy=BackoffStrategy.FIXED, initial_delay_seconds=3.0)
        policy = ExponentialRetryPolicy(cfg)
        assert policy.get_delay(1) == 3.0
        assert policy.get_delay(5) == 3.0

    def test_linear_backoff(self) -> None:
        cfg = RetryConfig(backoff_strategy=BackoffStrategy.LINEAR, initial_delay_seconds=2.0)
        policy = ExponentialRetryPolicy(cfg)
        assert policy.get_delay(2) == 4.0
        assert policy.get_delay(3) == 6.0

    def test_jitter_backoff_within_range(self) -> None:
        cfg = RetryConfig(
            backoff_strategy=BackoffStrategy.JITTER,
            initial_delay_seconds=2.0,
            max_delay_seconds=60.0,
        )
        policy = ExponentialRetryPolicy(cfg)
        for _ in range(10):
            d = policy.get_delay(1)
            assert 1.0 <= d <= 2.0


# ── F-036: SecretResolver ─────────────────────────────────────────────────────


class TestSecretResolver:
    def test_resolves_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MY_API_KEY", "sk-test-value")
        ref = SecretReference(secret_store=SecretStoreType.ENV, secret_key="MY_API_KEY")
        value = SecretResolver.resolve(ref, provider_type="openai")
        assert value == "sk-test-value"

    def test_raises_when_env_var_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MISSING_KEY", raising=False)
        ref = SecretReference(secret_store=SecretStoreType.ENV, secret_key="MISSING_KEY")
        with pytest.raises(AuthenticationError) as exc_info:
            SecretResolver.resolve(ref, provider_type="openai")
        assert "MISSING_KEY" in str(exc_info.value)

    def test_raises_when_env_var_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EMPTY_KEY", "")
        ref = SecretReference(secret_store=SecretStoreType.ENV, secret_key="EMPTY_KEY")
        with pytest.raises(AuthenticationError):
            SecretResolver.resolve(ref, provider_type="openai")

    def test_unsupported_store_raises(self) -> None:
        ref = SecretReference(secret_store=SecretStoreType.VAULT, secret_key="path/to/key")
        with pytest.raises(AuthenticationError) as exc_info:
            SecretResolver.resolve(ref, provider_type="openai")
        assert "not supported" in str(exc_info.value)


# ── F-036: CredentialValidator ────────────────────────────────────────────────


class TestCredentialValidatorOpenAI:
    def test_valid_sk_key(self) -> None:
        CredentialValidator.validate_openai_key("sk-" + "x" * 30)

    def test_valid_sk_proj_key(self) -> None:
        CredentialValidator.validate_openai_key("sk-proj-" + "x" * 30)

    def test_invalid_prefix_raises(self) -> None:
        with pytest.raises(InvalidRequestError) as exc_info:
            CredentialValidator.validate_openai_key("pk-invalid-key")
        assert "sk-" in str(exc_info.value)
        assert "pk-invalid-key" not in str(exc_info.value)

    def test_too_short_raises(self) -> None:
        with pytest.raises(InvalidRequestError) as exc_info:
            CredentialValidator.validate_openai_key("sk-short")
        assert "too short" in str(exc_info.value)

    def test_key_value_not_in_error(self) -> None:
        secret = "pk-mysecretkey12345678"  # wrong prefix — deliberately invalid
        with pytest.raises(InvalidRequestError) as exc_info:
            CredentialValidator.validate_openai_key(secret)
        assert secret not in str(exc_info.value)


class TestCredentialValidatorAnthropic:
    def test_valid_ant_key(self) -> None:
        CredentialValidator.validate_anthropic_key("sk-ant-" + "x" * 30)

    def test_invalid_prefix_raises(self) -> None:
        with pytest.raises(InvalidRequestError) as exc_info:
            CredentialValidator.validate_anthropic_key("sk-invalid-key-here")
        assert "sk-ant-" in str(exc_info.value)

    def test_too_short_raises(self) -> None:
        with pytest.raises(InvalidRequestError):
            CredentialValidator.validate_anthropic_key("sk-ant-x")

    def test_key_value_not_in_error(self) -> None:
        secret = "sk-ant-mysecret"
        with pytest.raises(InvalidRequestError) as exc_info:
            CredentialValidator.validate_anthropic_key(secret)
        assert secret not in str(exc_info.value)


# ── F-040: ProviderInfo ───────────────────────────────────────────────────────


class TestProviderInfo:
    def _caps(self, **kwargs: object) -> ProviderCapabilities:
        return ProviderCapabilities(**kwargs)  # type: ignore[arg-type]

    def test_from_capabilities_openai(self) -> None:
        caps = ProviderCapabilities(
            supports_streaming=True,
            supports_vision=True,
            max_context_window=128000,
            supported_model_ids=frozenset({"gpt-4o", "gpt-4o-mini"}),
        )
        info = ProviderInfo.from_capabilities(
            provider="openai",
            display_name="OpenAI",
            capabilities=caps,
            health=HealthStatus.HEALTHY,
        )
        assert info.provider == "openai"
        assert info.supports_streaming is True
        assert info.supports_vision is True
        assert info.max_context_window == 128000
        assert set(info.supported_model_ids) == {"gpt-4o", "gpt-4o-mini"}
        assert info.health == HealthStatus.HEALTHY

    def test_from_capabilities_sorted_model_ids(self) -> None:
        caps = ProviderCapabilities(supported_model_ids=frozenset({"zzz", "aaa", "mmm"}))
        info = ProviderInfo.from_capabilities(
            provider="test", display_name="Test", capabilities=caps
        )
        assert info.supported_model_ids == ["aaa", "mmm", "zzz"]

    def test_default_health_is_unknown(self) -> None:
        caps = ProviderCapabilities()
        info = ProviderInfo.from_capabilities(
            provider="test", display_name="Test", capabilities=caps
        )
        assert info.health == HealthStatus.UNKNOWN

    def test_fields_are_frozen(self) -> None:
        caps = ProviderCapabilities()
        info = ProviderInfo.from_capabilities(
            provider="test", display_name="Test", capabilities=caps
        )
        with pytest.raises((AttributeError, TypeError, ValueError)):
            info.provider = "changed"  # type: ignore[misc]

    def test_api_version_and_docs_url(self) -> None:
        caps = ProviderCapabilities()
        info = ProviderInfo.from_capabilities(
            provider="test",
            display_name="Test",
            capabilities=caps,
            api_version="2024-01",
            documentation_url="https://docs.example.com",
        )
        assert info.api_version == "2024-01"
        assert info.documentation_url == "https://docs.example.com"


# ── F-034: OpenAI adapter ─────────────────────────────────────────────────────


class TestOpenAIProvider:
    def _make_provider(
        self, transport: httpx.AsyncBaseTransport, key: str = _VALID_OPENAI_KEY
    ):  # type: ignore[no-untyped-def]
        from app.providers.adapters.openai import OpenAIProvider

        config = OpenAIConfig(
            provider_type="openai",
            display_name="OpenAI",
            api_key_ref=SecretReference(
                secret_store=SecretStoreType.ENV, secret_key="TEST_OPENAI_KEY"
            ),
        )
        return OpenAIProvider(config, http_transport=transport)

    @pytest.mark.asyncio
    async def test_verify_auth_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_OPENAI_KEY", _VALID_OPENAI_KEY)
        transport = _mock_transport([_make_response(200, {"data": []})])
        provider = self._make_provider(transport)
        result = await provider.verify_auth()
        assert result is True

    @pytest.mark.asyncio
    async def test_verify_auth_invalid_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_OPENAI_KEY", "bad-key")
        transport = _mock_transport([_make_response(401)])
        provider = self._make_provider(transport)
        with pytest.raises(InvalidRequestError):
            await provider.verify_auth()

    @pytest.mark.asyncio
    async def test_verify_auth_401_raises_auth_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TEST_OPENAI_KEY", _VALID_OPENAI_KEY)
        transport = _mock_transport([_make_response(401)])
        provider = self._make_provider(transport)
        with pytest.raises(AuthenticationError):
            await provider.verify_auth()

    @pytest.mark.asyncio
    async def test_check_connection_success_sets_healthy(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TEST_OPENAI_KEY", _VALID_OPENAI_KEY)
        transport = _mock_transport([_make_response(200, {"data": []})])
        provider = self._make_provider(transport)
        status = await provider.check_connection()
        assert status.is_connected is True
        assert status.health_status == HealthStatus.HEALTHY
        assert provider.is_healthy is True

    @pytest.mark.asyncio
    async def test_check_connection_failure_sets_unhealthy(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TEST_OPENAI_KEY", _VALID_OPENAI_KEY)
        transport = _mock_transport([_make_response(401)])
        provider = self._make_provider(transport)
        status = await provider.check_connection()
        assert status.is_connected is False
        assert status.health_status == HealthStatus.UNHEALTHY
        assert provider.is_healthy is False

    @pytest.mark.asyncio
    async def test_is_healthy_starts_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_OPENAI_KEY", _VALID_OPENAI_KEY)
        transport = _mock_transport([])
        provider = self._make_provider(transport)
        assert provider.is_healthy is False

    @pytest.mark.asyncio
    async def test_list_models_enriches_known_models(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TEST_OPENAI_KEY", _VALID_OPENAI_KEY)
        raw = {"data": [{"id": "gpt-4o"}, {"id": "gpt-4o-mini"}, {"id": "gpt-unknown-xyz"}]}
        transport = _mock_transport([_make_response(200, raw)])
        provider = self._make_provider(transport)
        models = await provider.list_models()
        assert len(models) == 3
        model_ids = {m.id for m in models}
        assert "gpt-4o" in model_ids
        assert "gpt-4o-mini" in model_ids
        assert "gpt-unknown-xyz" in model_ids
        # Known model should have display name
        gpt4o = next(m for m in models if m.id == "gpt-4o")
        assert gpt4o.display_name == "GPT-4o"
        assert gpt4o.context_window == 128000
        # Unknown model falls back to id as display name
        unknown = next(m for m in models if m.id == "gpt-unknown-xyz")
        assert unknown.display_name == "gpt-unknown-xyz"

    @pytest.mark.asyncio
    async def test_list_models_skips_entries_without_id(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TEST_OPENAI_KEY", _VALID_OPENAI_KEY)
        raw = {"data": [{"id": "gpt-4o"}, {"no_id": True}]}
        transport = _mock_transport([_make_response(200, raw)])
        provider = self._make_provider(transport)
        models = await provider.list_models()
        assert len(models) == 1

    @pytest.mark.asyncio
    async def test_check_capability_streaming(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_OPENAI_KEY", _VALID_OPENAI_KEY)
        provider = self._make_provider(_mock_transport([]))
        assert await provider.check_capability("streaming") is True

    @pytest.mark.asyncio
    async def test_check_capability_unknown(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_OPENAI_KEY", _VALID_OPENAI_KEY)
        provider = self._make_provider(_mock_transport([]))
        assert await provider.check_capability("nonexistent_cap") is False

    def test_get_provider_info_structure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_OPENAI_KEY", _VALID_OPENAI_KEY)
        provider = self._make_provider(_mock_transport([]))
        info = provider.get_provider_info()
        assert info.provider == "openai"
        assert info.api_version == "v1"
        assert info.documentation_url is not None
        assert info.supports_streaming is True
        assert info.supports_vision is True

    def test_get_provider_info_health_unknown_before_check(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TEST_OPENAI_KEY", _VALID_OPENAI_KEY)
        provider = self._make_provider(_mock_transport([]))
        info = provider.get_provider_info()
        assert info.health == HealthStatus.UNKNOWN

    def test_provider_type(self) -> None:
        from app.providers.adapters.openai import OpenAIProvider
        from app.models.provider_connection import ProviderType

        config = OpenAIConfig(provider_type="openai", display_name="OpenAI")
        provider = OpenAIProvider(config)
        assert provider.provider_type == ProviderType.OPENAI

    @pytest.mark.asyncio
    async def test_complete_raises_not_implemented(self) -> None:
        from app.providers.adapters.openai import OpenAIProvider
        from app.providers.models import Message, MessageRole, ProviderRequest

        config = OpenAIConfig(provider_type="openai", display_name="OpenAI")
        provider = OpenAIProvider(config)
        req = ProviderRequest(
            model_id="gpt-4o",
            messages=[Message(role=MessageRole.USER, content="hi")],
        )
        with pytest.raises(NotImplementedError):
            await provider.complete(req)

    @pytest.mark.asyncio
    async def test_no_api_key_ref_raises_auth_error(self) -> None:
        from app.providers.adapters.openai import OpenAIProvider

        config = OpenAIConfig(provider_type="openai", display_name="OpenAI")
        provider = OpenAIProvider(config)
        with pytest.raises(AuthenticationError):
            await provider.verify_auth()


# ── F-035: Anthropic adapter ──────────────────────────────────────────────────


class TestAnthropicProvider:
    def _make_provider(
        self, transport: httpx.AsyncBaseTransport, key: str = _VALID_ANTHROPIC_KEY
    ):  # type: ignore[no-untyped-def]
        from app.providers.adapters.anthropic import AnthropicProvider

        config = AnthropicConfig(
            provider_type="anthropic",
            display_name="Anthropic",
            api_key_ref=SecretReference(
                secret_store=SecretStoreType.ENV, secret_key="TEST_ANT_KEY"
            ),
        )
        return AnthropicProvider(config, http_transport=transport)

    @pytest.mark.asyncio
    async def test_verify_auth_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_ANT_KEY", _VALID_ANTHROPIC_KEY)
        transport = _mock_transport([_make_response(200, {"data": []})])
        provider = self._make_provider(transport)
        result = await provider.verify_auth()
        assert result is True

    @pytest.mark.asyncio
    async def test_verify_auth_invalid_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_ANT_KEY", "bad-ant-key")
        transport = _mock_transport([_make_response(401)])
        provider = self._make_provider(transport)
        with pytest.raises(InvalidRequestError):
            await provider.verify_auth()

    @pytest.mark.asyncio
    async def test_check_connection_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_ANT_KEY", _VALID_ANTHROPIC_KEY)
        transport = _mock_transport([_make_response(200, {"data": []})])
        provider = self._make_provider(transport)
        conn = await provider.check_connection()
        assert conn.is_connected is True
        assert conn.health_status == HealthStatus.HEALTHY
        assert provider.is_healthy is True

    @pytest.mark.asyncio
    async def test_check_connection_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_ANT_KEY", _VALID_ANTHROPIC_KEY)
        transport = _mock_transport([_make_response(403)])
        provider = self._make_provider(transport)
        conn = await provider.check_connection()
        assert conn.is_connected is False
        assert provider.is_healthy is False

    @pytest.mark.asyncio
    async def test_list_models_enriches_known_models(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TEST_ANT_KEY", _VALID_ANTHROPIC_KEY)
        raw = {
            "data": [
                {"id": "claude-3-5-sonnet-20241022"},
                {"id": "claude-3-unknown"},
            ]
        }
        transport = _mock_transport([_make_response(200, raw)])
        provider = self._make_provider(transport)
        models = await provider.list_models()
        assert len(models) == 2
        sonnet = next(m for m in models if m.id == "claude-3-5-sonnet-20241022")
        assert sonnet.display_name == "Claude 3.5 Sonnet"
        assert sonnet.context_window == 200000
        assert sonnet.max_output_tokens == 8192

    @pytest.mark.asyncio
    async def test_check_capability_vision(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_ANT_KEY", _VALID_ANTHROPIC_KEY)
        provider = self._make_provider(_mock_transport([]))
        assert await provider.check_capability("vision") is True

    @pytest.mark.asyncio
    async def test_check_capability_audio_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_ANT_KEY", _VALID_ANTHROPIC_KEY)
        provider = self._make_provider(_mock_transport([]))
        assert await provider.check_capability("audio") is False

    def test_get_provider_info_structure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_ANT_KEY", _VALID_ANTHROPIC_KEY)
        provider = self._make_provider(_mock_transport([]))
        info = provider.get_provider_info()
        assert info.provider == "anthropic"
        assert info.api_version == "2023-06-01"
        assert info.documentation_url is not None
        assert info.supports_streaming is True
        assert info.supports_audio is False

    def test_anthropic_version_from_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_ANT_KEY", _VALID_ANTHROPIC_KEY)
        from app.providers.adapters.anthropic import AnthropicProvider

        config = AnthropicConfig(
            provider_type="anthropic",
            display_name="Anthropic",
            anthropic_version="2024-01-01",
        )
        provider = AnthropicProvider(config)
        info = provider.get_provider_info()
        assert info.api_version == "2024-01-01"

    def test_provider_type(self) -> None:
        from app.providers.adapters.anthropic import AnthropicProvider
        from app.models.provider_connection import ProviderType

        config = AnthropicConfig(provider_type="anthropic", display_name="Anthropic")
        provider = AnthropicProvider(config)
        assert provider.provider_type == ProviderType.ANTHROPIC

    @pytest.mark.asyncio
    async def test_no_api_key_ref_raises_auth_error(self) -> None:
        from app.providers.adapters.anthropic import AnthropicProvider

        config = AnthropicConfig(provider_type="anthropic", display_name="Anthropic")
        provider = AnthropicProvider(config)
        with pytest.raises(AuthenticationError):
            await provider.verify_auth()

    @pytest.mark.asyncio
    async def test_complete_raises_not_implemented(self) -> None:
        from app.providers.adapters.anthropic import AnthropicProvider
        from app.providers.models import Message, MessageRole, ProviderRequest

        config = AnthropicConfig(provider_type="anthropic", display_name="Anthropic")
        provider = AnthropicProvider(config)
        req = ProviderRequest(
            model_id="claude-3-5-sonnet-20241022",
            messages=[Message(role=MessageRole.USER, content="hi")],
        )
        with pytest.raises(NotImplementedError):
            await provider.complete(req)


# ── F-033: HttpxTransport ─────────────────────────────────────────────────────


class TestHttpxTransport:
    @pytest.mark.asyncio
    async def test_get_with_mock_transport(self) -> None:
        transport = _mock_transport([_make_response(200, {"hello": "world"})])
        t = HttpxTransport(base_url="https://api.example.com", mock_transport=transport)
        resp = await t.request("GET", "/test")
        assert resp.status_code == 200
        await t.aclose()

    @pytest.mark.asyncio
    async def test_aclose_is_idempotent(self) -> None:
        transport = HttpxTransport(base_url="https://api.example.com")
        await transport.aclose()
        await transport.aclose()


# ── API endpoint tests ────────────────────────────────────────────────────────


class TestProvidersAPI:
    """Tests for the /v1/providers API endpoints using ASGI test client."""

    @pytest.mark.asyncio
    async def test_info_openai(self, client) -> None:  # type: ignore[no-untyped-def]
        resp = await client.get("/v1/providers/openai/info")
        assert resp.status_code == 200
        body = resp.json()
        assert body["provider"] == "openai"
        assert "supports_streaming" in body
        assert "api_version" in body

    @pytest.mark.asyncio
    async def test_info_anthropic(self, client) -> None:  # type: ignore[no-untyped-def]
        resp = await client.get("/v1/providers/anthropic/info")
        assert resp.status_code == 200
        body = resp.json()
        assert body["provider"] == "anthropic"
        assert body["api_version"] == "2023-06-01"

    @pytest.mark.asyncio
    async def test_info_unsupported_provider_returns_404(self, client) -> None:  # type: ignore[no-untyped-def]
        resp = await client.get("/v1/providers/fakeprovider/info")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_test_endpoint_unsupported_returns_404(self, client) -> None:  # type: ignore[no-untyped-def]
        resp = await client.post("/v1/providers/fakeprovider/test")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_models_endpoint_unsupported_returns_404(self, client) -> None:  # type: ignore[no-untyped-def]
        resp = await client.get("/v1/providers/fakeprovider/models")
        assert resp.status_code == 404


# ── PH-01: Shared HTTP transport ──────────────────────────────────────────────


class TestSharedTransport:
    """PH-01: adapter creates one HttpxTransport, ProviderHttpClient doesn't own it."""

    def test_openai_adapter_creates_transport_on_init(self) -> None:
        from app.providers.adapters.openai import OpenAIProvider

        cfg = OpenAIConfig(provider_type="openai", display_name="OpenAI")
        provider = OpenAIProvider(cfg)
        assert hasattr(provider, "_transport")
        assert isinstance(provider._transport, HttpxTransport)

    def test_anthropic_adapter_creates_transport_on_init(self) -> None:
        from app.providers.adapters.anthropic import AnthropicProvider

        cfg = AnthropicConfig(provider_type="anthropic", display_name="Anthropic")
        provider = AnthropicProvider(cfg)
        assert hasattr(provider, "_transport")
        assert isinstance(provider._transport, HttpxTransport)

    @pytest.mark.asyncio
    async def test_openai_adapter_aclose_closes_transport(self) -> None:
        from app.providers.adapters.openai import OpenAIProvider

        mock = _mock_transport([_make_response(200, {"data": []})])
        cfg = OpenAIConfig(provider_type="openai", display_name="OpenAI")
        provider = OpenAIProvider(cfg, http_transport=mock)
        await provider.aclose()

    @pytest.mark.asyncio
    async def test_openai_adapter_context_manager(self) -> None:
        from app.providers.adapters.openai import OpenAIProvider

        cfg = OpenAIConfig(provider_type="openai", display_name="OpenAI")
        async with OpenAIProvider(cfg) as provider:
            assert isinstance(provider, OpenAIProvider)

    @pytest.mark.asyncio
    async def test_anthropic_adapter_context_manager(self) -> None:
        from app.providers.adapters.anthropic import AnthropicProvider

        cfg = AnthropicConfig(provider_type="anthropic", display_name="Anthropic")
        async with AnthropicProvider(cfg) as provider:
            assert isinstance(provider, AnthropicProvider)

    @pytest.mark.asyncio
    async def test_client_does_not_own_shared_transport(self) -> None:
        transport = HttpxTransport(base_url="https://api.openai.com")
        client = ProviderHttpClient(
            base_url="https://api.openai.com",
            auth=BearerTokenAuth("sk-test"),
            provider_type="openai",
            transport=transport,
        )
        assert client._owns_transport is False
        await client.aclose()
        await transport.aclose()

    def test_client_owns_transport_when_none_provided(self) -> None:
        client = ProviderHttpClient(
            base_url="https://api.openai.com",
            auth=BearerTokenAuth("sk-test"),
            provider_type="openai",
        )
        assert client._owns_transport is True


# ── PH-02: Retry integration ──────────────────────────────────────────────────


class TestProviderHttpClientRetry:
    """PH-02: retry loop wired into ProviderHttpClient."""

    @pytest.mark.asyncio
    async def test_retries_on_503_then_succeeds(self) -> None:
        responses = [
            _make_response(503),
            _make_response(200, {"data": []}),
        ]
        transport = _mock_transport(responses)
        policy = ExponentialRetryPolicy(
            RetryConfig(max_attempts=3, initial_delay_seconds=0.0)
        )
        async with ProviderHttpClient(
            base_url="https://api.openai.com",
            auth=BearerTokenAuth("sk-test"),
            provider_type="openai",
            mock_transport=transport,
            retry_policy=policy,
        ) as client:
            result = await client.get("/v1/models")
        assert result == {"data": []}

    @pytest.mark.asyncio
    async def test_exhausts_retry_budget_on_repeated_503(self) -> None:
        from app.providers.errors import InternalProviderError

        responses = [_make_response(503)] * 4
        transport = _mock_transport(responses)
        policy = ExponentialRetryPolicy(
            RetryConfig(max_attempts=3, initial_delay_seconds=0.0)
        )
        async with ProviderHttpClient(
            base_url="https://api.openai.com",
            auth=BearerTokenAuth("sk-test"),
            provider_type="openai",
            mock_transport=transport,
            retry_policy=policy,
        ) as client:
            with pytest.raises(ProviderError):
                await client.get("/v1/models")

    @pytest.mark.asyncio
    async def test_no_retry_on_401(self) -> None:
        responses = [_make_response(401), _make_response(200, {"data": []})]
        transport = _mock_transport(responses)
        policy = ExponentialRetryPolicy(
            RetryConfig(max_attempts=3, initial_delay_seconds=0.0)
        )
        async with ProviderHttpClient(
            base_url="https://api.openai.com",
            auth=BearerTokenAuth("sk-bad"),
            provider_type="openai",
            mock_transport=transport,
            retry_policy=policy,
        ) as client:
            with pytest.raises(AuthenticationError):
                await client.get("/v1/models")

    @pytest.mark.asyncio
    async def test_no_retry_on_404(self) -> None:
        responses = [_make_response(404), _make_response(200, {"data": []})]
        transport = _mock_transport(responses)
        policy = ExponentialRetryPolicy(
            RetryConfig(max_attempts=3, initial_delay_seconds=0.0)
        )
        async with ProviderHttpClient(
            base_url="https://api.openai.com",
            auth=BearerTokenAuth("sk-test"),
            provider_type="openai",
            mock_transport=transport,
            retry_policy=policy,
        ) as client:
            with pytest.raises(InvalidRequestError):
                await client.get("/v1/missing")

    @pytest.mark.asyncio
    async def test_retries_on_429_with_retry_after(self) -> None:
        responses = [
            _make_response(429, headers={"Retry-After": "0"}),
            _make_response(200, {"data": []}),
        ]
        transport = _mock_transport(responses)
        policy = ExponentialRetryPolicy(
            RetryConfig(max_attempts=3, initial_delay_seconds=0.0)
        )
        async with ProviderHttpClient(
            base_url="https://api.openai.com",
            auth=BearerTokenAuth("sk-test"),
            provider_type="openai",
            mock_transport=transport,
            retry_policy=policy,
        ) as client:
            result = await client.get("/v1/models")
        assert result == {"data": []}


# ── PH-03: Factory enforcement ────────────────────────────────────────────────


class TestFactoryEnforcement:
    """PH-03: adapters always created via ProviderFactory(registry).create(config)."""

    def test_factory_creates_openai_adapter(self) -> None:
        from app.providers.adapters.openai import OpenAIProvider
        from app.providers.factory import ProviderFactory
        from app.providers.registry import get_registry

        cfg = OpenAIConfig(provider_type="openai", display_name="OpenAI")
        adapter = ProviderFactory(get_registry()).create(cfg)
        assert isinstance(adapter, OpenAIProvider)

    def test_factory_creates_anthropic_adapter(self) -> None:
        from app.providers.adapters.anthropic import AnthropicProvider
        from app.providers.factory import ProviderFactory
        from app.providers.registry import get_registry

        cfg = AnthropicConfig(provider_type="anthropic", display_name="Anthropic")
        adapter = ProviderFactory(get_registry()).create(cfg)
        assert isinstance(adapter, AnthropicProvider)

    def test_factory_raises_on_type_mismatch(self) -> None:
        from app.providers.errors import ProviderConfigurationError
        from app.providers.factory import ProviderFactory
        from app.providers.registry import ProviderRegistry

        from app.providers.adapters.anthropic import AnthropicProvider

        registry = ProviderRegistry()
        registry.register("openai", AnthropicProvider)

        cfg = OpenAIConfig(provider_type="openai", display_name="OpenAI")
        with pytest.raises(ProviderConfigurationError):
            ProviderFactory(registry).create(cfg)


# ── PH-05/06: Hardened API endpoints ─────────────────────────────────────────


class TestProvidersAPIHardened:
    """PH-05: grok/azure_openai are known ProviderType values but not production-ready.
    PH-06: missing API key returns 401, not 200 with auth_valid=false.
    """

    @pytest.mark.asyncio
    async def test_grok_info_returns_404(self, client) -> None:  # type: ignore[no-untyped-def]
        resp = await client.get("/v1/providers/grok/info")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_azure_openai_info_returns_404(self, client) -> None:  # type: ignore[no-untyped-def]
        resp = await client.get("/v1/providers/azure_openai/info")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_grok_test_returns_404(self, client) -> None:  # type: ignore[no-untyped-def]
        resp = await client.post("/v1/providers/grok/test")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_openai_test_without_key_returns_401(self, client, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        resp = await client.post("/v1/providers/openai/test")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_anthropic_test_without_key_returns_401(self, client, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        resp = await client.post("/v1/providers/anthropic/test")
        assert resp.status_code == 401
