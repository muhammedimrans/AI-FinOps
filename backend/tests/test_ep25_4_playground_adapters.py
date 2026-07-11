"""Tests for adapter.complete() — EP-25.4 (AI Playground).

Every provider's ``complete()`` implementation is exercised against a
mocked HTTP transport (no real network calls), confirming: (1) the correct
endpoint/payload shape is sent, (2) the response is normalized into a
provider-agnostic ``ProviderResponse``/``UsageData``, and (3) provider-
specific request shaping (Anthropic's top-level ``system`` field, Google's
``contents``/``systemInstruction``, Azure's deployment-scoped path) is
applied correctly.
"""

from __future__ import annotations

import json

import httpx
import pytest

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
    SecretReference,
    SecretStoreType,
)
from app.providers.models import Message, MessageRole, ProviderRequest


def _key_ref(value: str) -> SecretReference:
    return SecretReference(secret_store=SecretStoreType.INLINE, lookup_key=value)


def _response(status_code: int, body: object) -> httpx.Response:
    resp = httpx.Response(status_code, content=json.dumps(body).encode())
    resp.request = httpx.Request("POST", "https://example.test/")
    return resp


def _mock_transport(capture: dict[str, object], body: object, status: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        capture["url"] = str(request.url)
        capture["body"] = json.loads(request.content or b"{}")
        return _response(status, body)

    return httpx.MockTransport(handler)


def _request(*, system: str | None = "You are helpful.") -> ProviderRequest:
    messages = []
    if system:
        messages.append(Message(role=MessageRole.SYSTEM, content=system))
    messages.append(Message(role=MessageRole.USER, content="Say hello"))
    return ProviderRequest(
        model_id="test-model", messages=messages, max_tokens=100, temperature=0.7
    )


class TestOpenAIComplete:
    @pytest.mark.asyncio
    async def test_complete_posts_chat_completions_and_normalizes(self) -> None:
        capture: dict[str, object] = {}
        body = {
            "model": "gpt-4o",
            "choices": [{"message": {"content": "Hello!"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        transport = _mock_transport(capture, body)
        config = OpenAIConfig(
            provider_type="openai", display_name="OpenAI", api_key_ref=_key_ref("sk-test")
        )
        provider = OpenAIProvider(config, http_transport=transport)
        result = await provider.complete(_request())
        await provider.aclose()

        assert capture["url"].endswith("/v1/chat/completions")  # type: ignore[union-attr]
        payload = capture["body"]
        assert payload["model"] == "test-model"  # type: ignore[index]
        assert payload["messages"][0]["role"] == "system"  # type: ignore[index]
        assert result.content == "Hello!"
        assert result.usage is not None
        assert result.usage.prompt_tokens == 10
        assert result.usage.completion_tokens == 5
        assert result.finish_reason == "stop"


class TestAnthropicComplete:
    @pytest.mark.asyncio
    async def test_system_prompt_becomes_top_level_field(self) -> None:
        capture: dict[str, object] = {}
        body = {
            "model": "claude-sonnet-4",
            "content": [{"type": "text", "text": "Hi there"}],
            "usage": {"input_tokens": 8, "output_tokens": 4},
        }
        transport = _mock_transport(capture, body)
        config = AnthropicConfig(
            provider_type="anthropic", display_name="Anthropic", api_key_ref=_key_ref("sk-ant-test")
        )
        provider = AnthropicProvider(config, http_transport=transport)
        result = await provider.complete(_request())
        await provider.aclose()

        payload = capture["body"]
        assert payload["system"] == "You are helpful."  # type: ignore[index]
        assert all(m["role"] != "system" for m in payload["messages"])  # type: ignore[index]
        assert result.content == "Hi there"
        assert result.usage is not None
        assert result.usage.total_tokens == 12


class TestOpenRouterComplete:
    @pytest.mark.asyncio
    async def test_complete_posts_chat_completions(self) -> None:
        capture: dict[str, object] = {}
        body = {
            "model": "anthropic/claude-sonnet-4",
            "choices": [{"message": {"content": "Routed!"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        }
        transport = _mock_transport(capture, body)
        config = OpenRouterConfig(
            provider_type="openrouter",
            display_name="OpenRouter",
            api_key_ref=_key_ref("sk-or-test"),
        )
        provider = OpenRouterProvider(config, http_transport=transport)
        result = await provider.complete(_request(system=None))
        await provider.aclose()

        assert capture["url"].endswith("/chat/completions")  # type: ignore[union-attr]
        assert result.content == "Routed!"


class TestGrokComplete:
    @pytest.mark.asyncio
    async def test_complete_posts_chat_completions(self) -> None:
        capture: dict[str, object] = {}
        body = {
            "model": "grok-4",
            "choices": [{"message": {"content": "Grok says hi"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 6, "completion_tokens": 3, "total_tokens": 9},
        }
        transport = _mock_transport(capture, body)
        config = GrokConfig(
            provider_type="grok", display_name="Grok", api_key_ref=_key_ref("xai-test")
        )
        provider = GrokProvider(config, http_transport=transport)
        result = await provider.complete(_request())
        await provider.aclose()

        assert result.content == "Grok says hi"
        assert result.usage is not None and result.usage.total_tokens == 9


class TestAzureOpenAIComplete:
    @pytest.mark.asyncio
    async def test_complete_posts_to_deployment_path(self) -> None:
        capture: dict[str, object] = {}
        body = {
            "model": "gpt-4o",
            "choices": [{"message": {"content": "From Azure"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
        }
        transport = _mock_transport(capture, body)
        config = AzureOpenAIConfig(
            provider_type="azure_openai",
            display_name="Azure OpenAI",
            azure_endpoint="https://my-resource.openai.azure.com",
            api_key_ref=_key_ref("azure-test"),
        )
        provider = AzureOpenAIProvider(config, http_transport=transport)
        request = ProviderRequest(
            model_id="my-gpt4-deployment",
            messages=[Message(role=MessageRole.USER, content="Hi")],
        )
        result = await provider.complete(request)
        await provider.aclose()

        assert "/openai/deployments/my-gpt4-deployment/chat/completions" in capture["url"]  # type: ignore[operator]
        assert result.content == "From Azure"


class TestGoogleComplete:
    @pytest.mark.asyncio
    async def test_complete_maps_contents_and_system_instruction(self) -> None:
        capture: dict[str, object] = {}
        body = {
            "candidates": [{"content": {"parts": [{"text": "Gemini reply"}]}}],
            "usageMetadata": {"promptTokenCount": 7, "candidatesTokenCount": 3},
        }
        transport = _mock_transport(capture, body)
        config = GoogleConfig(
            provider_type="google", display_name="Google Gemini", api_key_ref=_key_ref("AIza-test")
        )
        provider = GoogleProvider(config, http_transport=transport)
        result = await provider.complete(_request())
        await provider.aclose()

        payload = capture["body"]
        assert payload["systemInstruction"]["parts"][0]["text"] == "You are helpful."  # type: ignore[index]
        assert payload["contents"][0]["role"] == "user"  # type: ignore[index]
        assert "key=" in capture["url"]  # type: ignore[operator]
        assert result.content == "Gemini reply"
        assert result.usage is not None
        assert result.usage.prompt_tokens == 7
        assert result.usage.completion_tokens == 3


class TestOllamaComplete:
    @pytest.mark.asyncio
    async def test_complete_posts_api_chat_non_streaming(self) -> None:
        capture: dict[str, object] = {}
        body = {
            "model": "llama3",
            "message": {"content": "Local reply"},
            "prompt_eval_count": 12,
            "eval_count": 6,
            "done": True,
        }
        transport = _mock_transport(capture, body)
        config = OllamaConfig(provider_type="ollama", display_name="Ollama")
        provider = OllamaProvider(config, http_transport=transport)
        request = ProviderRequest(
            model_id="llama3", messages=[Message(role=MessageRole.USER, content="Hi")]
        )
        result = await provider.complete(request)
        await provider.aclose()

        assert capture["url"].endswith("/api/chat")  # type: ignore[union-attr]
        assert capture["body"]["stream"] is False  # type: ignore[index]
        assert result.content == "Local reply"
        assert result.usage is not None
        assert result.usage.prompt_tokens == 12
        assert result.usage.completion_tokens == 6
        assert result.finish_reason == "stop"
