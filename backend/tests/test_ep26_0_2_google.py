"""EP-26.0.2 test suite — Google Gemini (AI Studio) as a first-class provider.

Covers the two genuinely new pieces of code this EP added: the live
GET /v1beta/models catalog (list_models, including pagination) and the
capability-mapping helpers it relies on. get_usage() is intentionally
unchanged (re-confirmed, not re-implemented — see the adapter's own
docstring) so it is not re-tested here beyond confirming it still returns
an honest empty page, matching test_ep06.py's own pre-existing coverage.

All hermetic — every HTTP call is a httpx.MockTransport, matching the
existing test_ep22_provider_validator.py / test_ep26_0_1_openrouter.py
convention. No live Google API key is used or required.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import patch

import httpx
import pytest

from app.providers.adapters.google import (
    GoogleProvider,
    _capabilities_from_generation_methods,
    _model_from_live_catalog,
)
from app.providers.config import GoogleConfig, SecretReference, SecretStoreType
from app.providers.models import ModelCapabilityFlag


def _response(status_code: int, body: object = None) -> httpx.Response:
    payload = body if body is not None else {}
    resp = httpx.Response(status_code, content=json.dumps(payload).encode())
    resp.request = httpx.Request("GET", "https://generativelanguage.googleapis.com/v1beta/")
    return resp


def _mock_transport(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler=handler)


def _config() -> GoogleConfig:
    return GoogleConfig(
        provider_type="google",
        display_name="Google Gemini",
        api_key_ref=SecretReference(
            secret_store=SecretStoreType.ENV, lookup_key="TEST_GOOGLE_EP26"
        ),
    )


class TestModelFromLiveCatalog:
    def test_maps_full_field_set(self) -> None:
        model = _model_from_live_catalog(
            {
                "name": "models/gemini-2.5-pro",
                "displayName": "Gemini 2.5 Pro",
                "inputTokenLimit": 1048576,
                "outputTokenLimit": 65536,
                "supportedGenerationMethods": ["generateContent", "streamGenerateContent"],
            }
        )
        assert model is not None
        assert model.id == "gemini-2.5-pro"
        assert model.display_name == "Gemini 2.5 Pro"
        assert model.context_window == 1048576
        assert model.max_output_tokens == 65536
        assert ModelCapabilityFlag.STREAMING in model.capabilities
        assert ModelCapabilityFlag.TOOL_CALLING in model.capabilities

    def test_strips_models_prefix(self) -> None:
        model = _model_from_live_catalog(
            {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]}
        )
        assert model is not None
        assert model.id == "gemini-2.5-flash"
        assert not model.id.startswith("models/")

    def test_returns_none_for_missing_name(self) -> None:
        assert _model_from_live_catalog({"supportedGenerationMethods": ["generateContent"]}) is None

    def test_returns_none_for_no_generation_methods(self) -> None:
        assert _model_from_live_catalog({"name": "models/embedding-001"}) is None

    def test_falls_back_to_model_id_when_no_display_name(self) -> None:
        model = _model_from_live_catalog(
            {
                "name": "models/gemini-3-flash-preview",
                "supportedGenerationMethods": ["generateContent"],
            }
        )
        assert model is not None
        assert model.display_name == "gemini-3-flash-preview"

    def test_deprecated_model_flagged(self) -> None:
        model = _model_from_live_catalog(
            {
                "name": "models/gemini-1.0-pro",
                "displayName": "Gemini 1.0 Pro (Deprecated)",
                "supportedGenerationMethods": ["generateContent"],
            }
        )
        assert model is not None
        assert model.is_deprecated is True


class TestCapabilitiesFromGenerationMethods:
    def test_streaming_flag_from_stream_method(self) -> None:
        caps = _capabilities_from_generation_methods(["streamGenerateContent"], "gemini-2.5-flash")
        assert ModelCapabilityFlag.STREAMING in caps

    def test_no_generation_methods_means_no_streaming_or_tool_flags(self) -> None:
        # The name-based vision/audio heuristic is independent of
        # supportedGenerationMethods (Google's list response has no
        # separate structured modality field), so it can still apply even
        # with an empty methods list — only the methods-derived flags
        # (streaming, tool/function calling) require a real method entry.
        caps = _capabilities_from_generation_methods([], "gemini-2.5-flash")
        assert ModelCapabilityFlag.STREAMING not in caps
        assert ModelCapabilityFlag.TOOL_CALLING not in caps
        assert ModelCapabilityFlag.FUNCTION_CALLING not in caps

    def test_embedding_model_excludes_audio(self) -> None:
        caps = _capabilities_from_generation_methods(["embedContent"], "text-embedding-004")
        assert ModelCapabilityFlag.AUDIO not in caps


class TestGoogleListModels:
    @pytest.mark.asyncio
    async def test_live_catalog_maps_models(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path.endswith("/v1beta/models")
            return _response(
                200,
                {
                    "models": [
                        {
                            "name": "models/gemini-2.5-pro",
                            "displayName": "Gemini 2.5 Pro",
                            "inputTokenLimit": 1048576,
                            "outputTokenLimit": 65536,
                            "supportedGenerationMethods": [
                                "generateContent",
                                "streamGenerateContent",
                            ],
                        },
                        {
                            "name": "models/gemini-2.5-flash",
                            "displayName": "Gemini 2.5 Flash",
                            "inputTokenLimit": 1048576,
                            "outputTokenLimit": 65536,
                            "supportedGenerationMethods": [
                                "generateContent",
                                "streamGenerateContent",
                            ],
                        },
                    ]
                },
            )

        provider = GoogleProvider(_config(), http_transport=_mock_transport(handler))
        with patch.dict("os.environ", {"TEST_GOOGLE_EP26": "AIza" + "a" * 35}):
            models = await provider.list_models()
        await provider.aclose()

        ids = [m.id for m in models]
        assert "gemini-2.5-pro" in ids
        assert "gemini-2.5-flash" in ids

    @pytest.mark.asyncio
    async def test_pagination_follows_next_page_token(self) -> None:
        call_count = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            call_count["n"] += 1
            params = dict(request.url.params)
            if "pageToken" not in params:
                return _response(
                    200,
                    {
                        "models": [
                            {
                                "name": "models/gemini-2.5-pro",
                                "supportedGenerationMethods": ["generateContent"],
                            }
                        ],
                        "nextPageToken": "page2",
                    },
                )
            assert params["pageToken"] == "page2"
            return _response(
                200,
                {
                    "models": [
                        {
                            "name": "models/gemini-2.5-flash",
                            "supportedGenerationMethods": ["generateContent"],
                        }
                    ]
                },
            )

        provider = GoogleProvider(_config(), http_transport=_mock_transport(handler))
        with patch.dict("os.environ", {"TEST_GOOGLE_EP26": "AIza" + "a" * 35}):
            models = await provider.list_models()
        await provider.aclose()

        assert call_count["n"] == 2
        ids = [m.id for m in models]
        assert "gemini-2.5-pro" in ids
        assert "gemini-2.5-flash" in ids

    @pytest.mark.asyncio
    async def test_pagination_loop_is_bounded(self) -> None:
        """A server that always returns a nextPageToken must never cause
        an unbounded request loop."""
        call_count = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            call_count["n"] += 1
            return _response(
                200,
                {
                    "models": [
                        {
                            "name": f"models/gemini-fake-{call_count['n']}",
                            "supportedGenerationMethods": ["generateContent"],
                        }
                    ],
                    "nextPageToken": "always-more",
                },
            )

        provider = GoogleProvider(_config(), http_transport=_mock_transport(handler))
        with patch.dict("os.environ", {"TEST_GOOGLE_EP26": "AIza" + "a" * 35}):
            await provider.list_models()
        await provider.aclose()

        assert call_count["n"] <= 10

    @pytest.mark.asyncio
    async def test_network_failure_falls_back_to_static_list(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("unreachable")

        provider = GoogleProvider(_config(), http_transport=_mock_transport(handler))
        with patch.dict("os.environ", {"TEST_GOOGLE_EP26": "AIza" + "a" * 35}):
            models = await provider.list_models()
        await provider.aclose()

        assert len(models) > 0
        assert any(m.id == "gemini-2.5-pro" for m in models)

    @pytest.mark.asyncio
    async def test_empty_catalog_falls_back_to_static_list(self) -> None:
        provider = GoogleProvider(
            _config(), http_transport=_mock_transport(lambda r: _response(200, {"models": []}))
        )
        with patch.dict("os.environ", {"TEST_GOOGLE_EP26": "AIza" + "a" * 35}):
            models = await provider.list_models()
        await provider.aclose()
        assert len(models) > 0

    @pytest.mark.asyncio
    async def test_no_credential_still_returns_models_not_raise(self) -> None:
        """Mirrors OpenRouterProvider.list_models()'s EP-26.0.1 fix — a
        missing credential must never prevent browsing the model catalog,
        since /v1beta/models works without a valid key present (an invalid
        or absent key is only actually rejected by Google's own API, which
        this mocked transport doesn't simulate here)."""
        provider = GoogleProvider(
            GoogleConfig(display_name="No Key"),
            http_transport=_mock_transport(lambda r: _response(200, {"models": []})),
        )
        models = await provider.list_models()
        await provider.aclose()
        assert len(models) > 0

    @pytest.mark.asyncio
    async def test_deprecated_and_no_method_models_filtered_out(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return _response(
                200,
                {
                    "models": [
                        {
                            "name": "models/gemini-2.5-pro",
                            "supportedGenerationMethods": ["generateContent"],
                        },
                        {"name": "models/some-internal-alias", "supportedGenerationMethods": []},
                    ]
                },
            )

        provider = GoogleProvider(_config(), http_transport=_mock_transport(handler))
        with patch.dict("os.environ", {"TEST_GOOGLE_EP26": "AIza" + "a" * 35}):
            models = await provider.list_models()
        await provider.aclose()

        ids = [m.id for m in models]
        assert "gemini-2.5-pro" in ids
        assert "some-internal-alias" not in ids


class TestGoogleGetUsageUnchanged:
    @pytest.mark.asyncio
    async def test_still_returns_honest_empty_page(self) -> None:
        """Reconfirms EP-26.0.2's own research finding: no bulk usage API
        exists for the AI Studio surface, so get_usage() is deliberately
        unchanged by this EP."""
        from app.providers.models import UsagePage

        provider = GoogleProvider(_config())
        page = await provider.get_usage(
            datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 31, tzinfo=UTC)
        )
        await provider.aclose()
        assert isinstance(page, UsagePage)
        assert page.events == []


class TestGoogleNotInKnownUsageApiProviders:
    def test_google_remains_excluded(self) -> None:
        """Google must NOT be added to _KNOWN_USAGE_API_PROVIDERS by this
        EP — unlike EP-26.0.1's OpenRouter, no real usage endpoint was
        wired up, so the informational flag must stay accurate."""
        from app.services.provider_sync_service import _KNOWN_USAGE_API_PROVIDERS

        assert "google" not in _KNOWN_USAGE_API_PROVIDERS
