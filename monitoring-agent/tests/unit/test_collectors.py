from __future__ import annotations

import httpx
import pytest

from costorah_agent.collectors.anthropic import AnthropicCollector
from costorah_agent.collectors.azure_openai import AzureOpenAICollector
from costorah_agent.collectors.google import GoogleCollector
from costorah_agent.collectors.ollama import OllamaCollector
from costorah_agent.collectors.openai import OpenAICollector
from costorah_agent.collectors.openrouter import OpenRouterCollector

# ── OpenAI ───────────────────────────────────────────────────────────────


def test_openai_normalize_builds_expected_event() -> None:
    collector = OpenAICollector({"api_key": "sk-admin-x"})
    raw = {
        "bucket": {"start_time": 1000, "end_time": 1060},
        "result": {
            "model": "gpt-4o",
            "input_tokens": 100,
            "output_tokens": 50,
            "num_model_requests": 3,
        },
    }
    event = collector.normalize(raw)
    assert event.provider == "openai"
    assert event.model == "gpt-4o"
    assert event.input_tokens == 100
    assert event.output_tokens == 50
    assert event.total_tokens == 150
    assert event.cost == 0.0
    assert event.metadata == {"request_count": 3, "bucket_start": 1000}


def test_openai_normalize_deterministic_for_same_bucket() -> None:
    collector = OpenAICollector({})
    raw = {
        "bucket": {"start_time": 1000, "end_time": 1060},
        "result": {"model": "gpt-4o", "input_tokens": 1, "output_tokens": 1},
    }
    assert collector.normalize(raw).request_id == collector.normalize(raw).request_id


async def test_openai_collect_without_api_key_returns_empty() -> None:
    collector = OpenAICollector({})
    events = await collector.collect()
    assert events == []
    health = await collector.health()
    assert health.healthy is False
    assert "not configured" in health.detail
    await collector.shutdown()


async def test_openai_collect_success_parses_buckets() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "start_time": 1000,
                        "end_time": 1060,
                        "results": [
                            {"model": "gpt-4o", "input_tokens": 5, "output_tokens": 2},
                        ],
                    }
                ]
            },
        )

    collector = OpenAICollector({"api_key": "sk-admin"}, transport=httpx.MockTransport(handler))
    events = await collector.collect()
    assert len(events) == 1
    assert events[0].model == "gpt-4o"
    health = await collector.health()
    assert health.healthy is True
    await collector.shutdown()


async def test_openai_collect_http_error_returns_empty_and_degrades_health() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    collector = OpenAICollector({"api_key": "sk-admin"}, transport=httpx.MockTransport(handler))
    events = await collector.collect()
    assert events == []
    health = await collector.health()
    assert health.healthy is False
    await collector.shutdown()


# ── OpenRouter ───────────────────────────────────────────────────────────


def test_openrouter_normalize_builds_aggregate_event() -> None:
    collector = OpenRouterCollector({})
    event = collector.normalize({"delta_cost": 1.2345, "label": "prod-key"})
    assert event.provider == "openrouter"
    assert event.model == "aggregate"
    assert event.cost == 1.2345
    assert event.metadata["granularity"] == "account_aggregate_delta"


async def test_openrouter_first_poll_establishes_baseline_no_event() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"usage": 10.0, "label": "k"}})

    collector = OpenRouterCollector({"api_key": "or-x"}, transport=httpx.MockTransport(handler))
    events = await collector.collect()
    assert events == []  # baseline poll never emits
    await collector.shutdown()


async def test_openrouter_second_poll_emits_delta() -> None:
    responses = iter(
        [
            httpx.Response(200, json={"data": {"usage": 10.0, "label": "k"}}),
            httpx.Response(200, json={"data": {"usage": 12.5, "label": "k"}}),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return next(responses)

    collector = OpenRouterCollector({"api_key": "or-x"}, transport=httpx.MockTransport(handler))
    await collector.collect()  # baseline
    events = await collector.collect()
    assert len(events) == 1
    assert events[0].cost == pytest.approx(2.5)
    await collector.shutdown()


async def test_openrouter_no_delta_emits_nothing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"usage": 10.0, "label": "k"}})

    collector = OpenRouterCollector({"api_key": "or-x"}, transport=httpx.MockTransport(handler))
    await collector.collect()
    events = await collector.collect()
    assert events == []
    await collector.shutdown()


async def test_openrouter_collect_without_api_key_returns_empty() -> None:
    collector = OpenRouterCollector({})
    assert await collector.collect() == []
    await collector.shutdown()


# ── Anthropic (real attempt, honest degradation) ────────────────────────


def test_anthropic_normalize_builds_expected_event() -> None:
    collector = AnthropicCollector({})
    raw = {
        "bucket": {"start_time": 1000, "end_time": 1060},
        "result": {
            "model": "claude-3-opus",
            "uncached_input_tokens": 20,
            "output_tokens": 10,
            "cache_read_input_tokens": 5,
        },
    }
    event = collector.normalize(raw)
    assert event.provider == "anthropic"
    assert event.input_tokens == 20
    assert event.cached_tokens == 5
    assert event.cost == 0.0


async def test_anthropic_collect_without_admin_key_returns_empty() -> None:
    collector = AnthropicCollector({})
    events = await collector.collect()
    assert events == []
    health = await collector.health()
    assert health.healthy is False
    await collector.shutdown()


async def test_anthropic_collect_error_silently_returns_empty() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": "forbidden"})

    collector = AnthropicCollector(
        {"admin_api_key": "sk-admin"}, transport=httpx.MockTransport(handler)
    )
    events = await collector.collect()
    assert events == []  # mirrors backend's EP-08 Anthropic adapter: silent on error
    health = await collector.health()
    assert health.healthy is False
    await collector.shutdown()


async def test_anthropic_collect_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "start_time": 1000,
                        "end_time": 1060,
                        "results": [{"model": "claude-3-opus", "output_tokens": 1}],
                    }
                ]
            },
        )

    collector = AnthropicCollector(
        {"admin_api_key": "sk-admin"}, transport=httpx.MockTransport(handler)
    )
    events = await collector.collect()
    assert len(events) == 1
    await collector.shutdown()


# ── Honest stubs: Google, Azure ──────────────────────────────────────────


@pytest.mark.parametrize("collector_cls", [GoogleCollector, AzureOpenAICollector])
async def test_stub_collector_always_returns_empty(collector_cls: type) -> None:
    collector = collector_cls({})
    assert await collector.collect() == []


@pytest.mark.parametrize("collector_cls", [GoogleCollector, AzureOpenAICollector])
async def test_stub_collector_health_is_unhealthy_with_explanation(
    collector_cls: type,
) -> None:
    collector = collector_cls({})
    health = await collector.health()
    assert health.healthy is False
    assert health.detail  # non-empty explanation, not silently blank


@pytest.mark.parametrize("collector_cls", [GoogleCollector, AzureOpenAICollector])
def test_stub_collector_normalize_raises_not_implemented(collector_cls: type) -> None:
    collector = collector_cls({})
    with pytest.raises(NotImplementedError):
        collector.normalize({})


# ── Ollama (real connectivity check, no usage API) ──────────────────────


async def test_ollama_collect_always_returns_empty_even_when_reachable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"models": []})

    collector = OllamaCollector({}, transport=httpx.MockTransport(handler))
    assert await collector.collect() == []
    await collector.shutdown()


async def test_ollama_health_reachable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"models": []})

    collector = OllamaCollector({}, transport=httpx.MockTransport(handler))
    health = await collector.health()
    assert health.healthy is True
    await collector.shutdown()


async def test_ollama_health_unreachable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    collector = OllamaCollector({}, transport=httpx.MockTransport(handler))
    health = await collector.health()
    assert health.healthy is False
    assert "unreachable" in health.detail
    await collector.shutdown()


def test_ollama_normalize_raises_not_implemented() -> None:
    collector = OllamaCollector({})
    with pytest.raises(NotImplementedError):
        collector.normalize({})
