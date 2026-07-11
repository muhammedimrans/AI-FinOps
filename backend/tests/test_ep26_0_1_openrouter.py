"""EP-26.0.1 test suite — OpenRouter as a first-class provider.

Covers the three genuinely new pieces of code this EP added: the live
GET /models catalog (list_models), the GET /api/v1/activity usage import
(get_usage), and OpenRouterUsageNormalizer's defensive field-name mapping.
All hermetic — every HTTP call is a httpx.MockTransport, matching the
existing test_ep22_provider_validator.py convention. No live OpenRouter
credential is used or required (see CLAUDE.md's EP-26.0.1 "Known
limitations" for why this environment cannot hold one).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import patch

import httpx
import pytest

from app.providers.adapters.openrouter import OpenRouterProvider
from app.providers.config import OpenRouterConfig, SecretReference, SecretStoreType
from app.usage.normalizer import OpenRouterUsageNormalizer, get_normalizer_registry


def _response(status_code: int, body: object = None) -> httpx.Response:
    payload = body if body is not None else {}
    resp = httpx.Response(status_code, content=json.dumps(payload).encode())
    resp.request = httpx.Request("GET", "https://openrouter.ai/api/v1/")
    return resp


def _mock_transport(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler=handler)


def _config() -> OpenRouterConfig:
    return OpenRouterConfig(
        provider_type="openrouter",
        display_name="OpenRouter",
        api_key_ref=SecretReference(secret_store=SecretStoreType.ENV, lookup_key="TEST_OR_EP26"),
    )


class TestOpenRouterUsageNormalizer:
    def test_normalizes_full_field_set(self) -> None:
        normalizer = OpenRouterUsageNormalizer()
        event = normalizer.normalize(
            {
                "date": "2026-07-10",
                "model": "anthropic/claude-sonnet-4",
                "provider_name": "anthropic",
                "prompt_tokens": 12000,
                "completion_tokens": 4500,
                "requests": 42,
            }
        )
        assert event.provider == "openrouter"
        assert event.model == "anthropic/claude-sonnet-4"
        assert event.prompt_tokens == 12000
        assert event.completion_tokens == 4500
        assert event.total_tokens == 16500
        assert event.request_count == 42
        assert event.metadata["underlying_vendor"] == "anthropic"
        assert event.timestamp == datetime(2026, 7, 10, tzinfo=UTC)

    def test_defensive_field_name_variants(self) -> None:
        """Tokens reported under the OpenAI-usage-style alt names still map."""
        normalizer = OpenRouterUsageNormalizer()
        event = normalizer.normalize(
            {
                "date": "2026-07-01",
                "model": "openai/gpt-4o",
                "input_tokens": 100,
                "output_tokens": 50,
                "num_requests": 3,
            }
        )
        assert event.prompt_tokens == 100
        assert event.completion_tokens == 50
        assert event.total_tokens == 150
        assert event.request_count == 3

    def test_missing_fields_default_to_zero_not_crash(self) -> None:
        normalizer = OpenRouterUsageNormalizer()
        event = normalizer.normalize({"model": "meta-llama/llama-3.1-405b-instruct"})
        assert event.prompt_tokens == 0
        assert event.completion_tokens == 0
        assert event.total_tokens == 0
        assert event.request_count == 1

    def test_underlying_vendor_derived_from_model_slug_when_absent(self) -> None:
        normalizer = OpenRouterUsageNormalizer()
        event = normalizer.normalize({"date": "2026-07-05", "model": "deepseek/deepseek-r1"})
        assert event.metadata["underlying_vendor"] == "deepseek"

    def test_provider_request_id_is_deterministic_hash_when_no_id(self) -> None:
        normalizer = OpenRouterUsageNormalizer()
        raw = {"date": "2026-07-05", "model": "google/gemini-2.5-pro"}
        first = normalizer.normalize(raw)
        second = normalizer.normalize(dict(raw))
        assert first.provider_request_id == second.provider_request_id
        assert first.provider_request_id != ""

    def test_registered_in_normalizer_registry(self) -> None:
        registry = get_normalizer_registry()
        assert "openrouter" in registry.supported_providers()
        assert registry.get("openrouter") is not None


class TestOpenRouterGetUsage:
    @pytest.mark.asyncio
    async def test_single_day_activity_normalizes_into_events(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path.endswith("/api/v1/activity")
            return _response(
                200,
                {
                    "data": [
                        {
                            "date": "2026-07-10",
                            "model": "anthropic/claude-sonnet-4",
                            "prompt_tokens": 500,
                            "completion_tokens": 200,
                            "requests": 5,
                        }
                    ]
                },
            )

        provider = OpenRouterProvider(_config(), http_transport=_mock_transport(handler))
        with patch.dict("os.environ", {"TEST_OR_EP26": "sk-or-" + "a" * 20}):
            page = await provider.get_usage(
                datetime(2026, 7, 10, tzinfo=UTC), datetime(2026, 7, 10, tzinfo=UTC)
            )
        await provider.aclose()

        assert len(page.events) == 1
        assert page.events[0].model == "anthropic/claude-sonnet-4"
        assert page.events[0].request_count == 5
        assert page.has_more is False
        assert page.next_cursor is None

    @pytest.mark.asyncio
    async def test_multi_day_range_issues_one_request_per_day(self) -> None:
        seen_dates: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            date_param = dict(request.url.params)["date"]
            seen_dates.append(date_param)
            return _response(200, {"data": [{"date": date_param, "model": "openai/gpt-4o"}]})

        provider = OpenRouterProvider(_config(), http_transport=_mock_transport(handler))
        with patch.dict("os.environ", {"TEST_OR_EP26": "sk-or-" + "a" * 20}):
            page = await provider.get_usage(
                datetime(2026, 7, 1, tzinfo=UTC), datetime(2026, 7, 3, tzinfo=UTC)
            )
        await provider.aclose()

        assert seen_dates == ["2026-07-01", "2026-07-02", "2026-07-03"]
        assert len(page.events) == 3

    @pytest.mark.asyncio
    async def test_authentication_error_for_one_day_skips_honestly_not_raises(self) -> None:
        """Simulates the disclosed 'standard key may lack /activity
        permission' scenario (CLAUDE.md's EP-26.0.1) — a 401 must degrade
        to zero events for that day, never propagate as a hard failure."""

        def handler(request: httpx.Request) -> httpx.Response:
            return _response(401, {"error": {"message": "insufficient permission"}})

        provider = OpenRouterProvider(_config(), http_transport=_mock_transport(handler))
        with patch.dict("os.environ", {"TEST_OR_EP26": "sk-or-" + "a" * 20}):
            page = await provider.get_usage(
                datetime(2026, 7, 10, tzinfo=UTC), datetime(2026, 7, 10, tzinfo=UTC)
            )
        await provider.aclose()

        assert page.events == []
        assert page.has_more is False

    @pytest.mark.asyncio
    async def test_network_error_for_one_day_does_not_abort_other_days(self) -> None:
        # Fail every attempt (including the HTTP client's own internal
        # retries — see ExponentialRetryPolicy) for 2026-07-01 specifically,
        # so day 1 permanently fails while day 2 always succeeds,
        # regardless of how many retries the failing day consumes.
        def handler(request: httpx.Request) -> httpx.Response:
            if dict(request.url.params).get("date") == "2026-07-01":
                raise httpx.ConnectError("boom")
            return _response(200, {"data": [{"date": "2026-07-02", "model": "openai/gpt-4o"}]})

        provider = OpenRouterProvider(_config(), http_transport=_mock_transport(handler))
        with patch.dict("os.environ", {"TEST_OR_EP26": "sk-or-" + "a" * 20}):
            page = await provider.get_usage(
                datetime(2026, 7, 1, tzinfo=UTC), datetime(2026, 7, 2, tzinfo=UTC)
            )
        await provider.aclose()

        assert len(page.events) == 1
        assert page.events[0].model == "openai/gpt-4o"

    @pytest.mark.asyncio
    async def test_retention_window_clamps_far_past_start_date(self) -> None:
        """A start_date far older than OpenRouter's documented 30-day
        retention must never trigger an unbounded per-day request loop."""
        seen_dates: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_dates.append(dict(request.url.params)["date"])
            return _response(200, {"data": []})

        provider = OpenRouterProvider(_config(), http_transport=_mock_transport(handler))
        with patch.dict("os.environ", {"TEST_OR_EP26": "sk-or-" + "a" * 20}):
            await provider.get_usage(
                datetime(2020, 1, 1, tzinfo=UTC), datetime(2026, 7, 10, tzinfo=UTC)
            )
        await provider.aclose()

        assert len(seen_dates) <= 31

    @pytest.mark.asyncio
    async def test_empty_data_array_returns_empty_events(self) -> None:
        provider = OpenRouterProvider(
            _config(), http_transport=_mock_transport(lambda r: _response(200, {"data": []}))
        )
        with patch.dict("os.environ", {"TEST_OR_EP26": "sk-or-" + "a" * 20}):
            page = await provider.get_usage(
                datetime(2026, 7, 10, tzinfo=UTC), datetime(2026, 7, 10, tzinfo=UTC)
            )
        await provider.aclose()
        assert page.events == []


class TestOpenRouterListModels:
    @pytest.mark.asyncio
    async def test_live_catalog_maps_pricing_and_context_window(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path.endswith("/models")
            return _response(
                200,
                {
                    "data": [
                        {
                            "id": "anthropic/claude-sonnet-4",
                            "name": "Claude Sonnet 4",
                            "context_length": 200000,
                            "pricing": {"prompt": "0.000003", "completion": "0.000015"},
                            "architecture": {"modality": "text+image->text"},
                            "supported_parameters": ["tools", "tool_choice"],
                        }
                    ]
                },
            )

        provider = OpenRouterProvider(_config(), http_transport=_mock_transport(handler))
        with patch.dict("os.environ", {"TEST_OR_EP26": "sk-or-" + "a" * 20}):
            models = await provider.list_models()
        await provider.aclose()

        assert len(models) == 1
        m = models[0]
        assert m.id == "anthropic/claude-sonnet-4"
        assert m.context_window == 200000
        assert m.input_cost_per_1k == pytest.approx(0.003)
        assert m.output_cost_per_1k == pytest.approx(0.015)
        from app.providers.models import ModelCapabilityFlag

        assert ModelCapabilityFlag.TOOL_CALLING in m.capabilities
        assert ModelCapabilityFlag.VISION in m.capabilities

    @pytest.mark.asyncio
    async def test_network_failure_falls_back_to_static_list(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("unreachable")

        provider = OpenRouterProvider(_config(), http_transport=_mock_transport(handler))
        with patch.dict("os.environ", {"TEST_OR_EP26": "sk-or-" + "a" * 20}):
            models = await provider.list_models()
        await provider.aclose()

        assert len(models) > 0
        assert any(m.id == "openai/gpt-4o" for m in models)

    @pytest.mark.asyncio
    async def test_empty_catalog_falls_back_to_static_list(self) -> None:
        provider = OpenRouterProvider(
            _config(), http_transport=_mock_transport(lambda r: _response(200, {"data": []}))
        )
        with patch.dict("os.environ", {"TEST_OR_EP26": "sk-or-" + "a" * 20}):
            models = await provider.list_models()
        await provider.aclose()
        assert len(models) > 0


class TestOpenRouterKnownUsageApiProviders:
    def test_openrouter_is_a_known_usage_api_provider(self) -> None:
        from app.services.provider_sync_service import _KNOWN_USAGE_API_PROVIDERS

        assert "openrouter" in _KNOWN_USAGE_API_PROVIDERS
        assert "openai" in _KNOWN_USAGE_API_PROVIDERS
        assert "anthropic" in _KNOWN_USAGE_API_PROVIDERS
        # Providers with genuinely no bulk usage endpoint on their own
        # platform remain excluded (CLAUDE.md's EP-24.3 accounting,
        # unaffected by this EP).
        assert "google" not in _KNOWN_USAGE_API_PROVIDERS
        assert "azure_openai" not in _KNOWN_USAGE_API_PROVIDERS
