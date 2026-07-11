"""EP-26.0.2.1 — end-to-end provider lifecycle validation (Google + OpenRouter).

Part 2 of EP-26.0.2.1's task asked for manual validation of real accounts;
no live Google AI Studio or OpenRouter credential is available in this
sandbox (confirmed by grepping the environment and every .env* file — see
CLAUDE.md's EP-26.0.2.1 section). This file is the disclosed substitute:
"validated mocks" per the task's own fallback instruction, chaining
together a single connection's full realistic lifecycle in one continuous
narrative per provider, rather than re-testing isolated methods the way
test_ep26_0_1_openrouter.py / test_ep26_0_2_google.py / test_ep22_provider_
validator.py already do (those files are NOT duplicated here — this file
only adds the sequencing those unit-level suites don't cover):

    connect (verify_auth succeeds)
      -> discover models (list_models)
      -> attempt usage collection (get_usage — real for OpenRouter, an
         honest no-op for Google)
      -> credential revoked server-side (verify_auth now 401)
      -> credential missing entirely (no key configured at all)

All hermetic — every HTTP call is httpx.MockTransport. No live credential
is used or required.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest

from app.providers.adapters.google import GoogleProvider
from app.providers.adapters.openrouter import OpenRouterProvider
from app.providers.config import GoogleConfig, OpenRouterConfig, SecretReference, SecretStoreType
from app.providers.errors import AuthenticationError
from app.providers.models import UsagePage


def _resp(status_code: int, body: object) -> httpx.Response:
    r = httpx.Response(status_code, content=json.dumps(body).encode())
    r.request = httpx.Request("GET", "https://example.invalid/")
    return r


def _google_config(env_var: str) -> GoogleConfig:
    return GoogleConfig(
        provider_type="google",
        display_name="Google Gemini — lifecycle test",
        api_key_ref=SecretReference(secret_store=SecretStoreType.ENV, lookup_key=env_var),
    )


def _openrouter_config(env_var: str) -> OpenRouterConfig:
    return OpenRouterConfig(
        provider_type="openrouter",
        display_name="OpenRouter — lifecycle test",
        api_key_ref=SecretReference(secret_store=SecretStoreType.ENV, lookup_key=env_var),
    )


class TestGoogleFullLifecycle:
    """Connect -> discover models -> attempt usage import -> key revoked."""

    @pytest.mark.asyncio
    async def test_connect_discover_then_credential_revoked(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("EP26021_GOOGLE_KEY", "AIza" + "a" * 35)
        state = {"revoked": False}

        def handler(request: httpx.Request) -> httpx.Response:
            if state["revoked"]:
                return _resp(401, {"error": {"message": "API key not valid"}})
            if request.url.path.endswith("/v1beta/models"):
                return _resp(
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
                            }
                        ]
                    },
                )
            return _resp(200, {})

        provider = GoogleProvider(
            _google_config("EP26021_GOOGLE_KEY"), http_transport=httpx.MockTransport(handler)
        )

        # 1. Connect — the connection form's "Test connection" probe.
        assert await provider.verify_auth() is True

        # 2. Discover models — the Connect Provider form's model picker.
        models = await provider.list_models()
        assert any(m.id == "gemini-2.5-pro" for m in models)

        # 3. Attempt usage import — must be an honest, non-crashing empty
        #    page (Part 4: "the dashboard must never imply usage exists
        #    when the provider does not expose it").
        page = await provider.get_usage(
            datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 31, tzinfo=UTC)
        )
        assert isinstance(page, UsagePage)
        assert page.events == []

        # 4. Credential revoked server-side (user deleted the key in AI
        #    Studio) — the next health check must surface this as an
        #    AuthenticationError, not a silent success or a crash.
        state["revoked"] = True
        with pytest.raises(AuthenticationError):
            await provider.verify_auth()

        await provider.aclose()

    @pytest.mark.asyncio
    async def test_missing_credential_still_allows_model_browsing(self) -> None:
        """A connection saved with no key at all (or one that failed to
        resolve) must still let a user browse the model catalog — the
        EP-26.0.1/EP-26.0.2 credential-fallback fix, re-pinned here as part
        of the lifecycle rather than in isolation."""
        provider = GoogleProvider(
            GoogleConfig(display_name="No key"),
            http_transport=httpx.MockTransport(
                lambda r: _resp(
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
            ),
        )
        models = await provider.list_models()
        assert len(models) > 0
        await provider.aclose()


class TestOpenRouterFullLifecycle:
    """Connect -> discover models -> import real usage -> key expires."""

    @pytest.mark.asyncio
    async def test_connect_discover_sync_then_credential_expired(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("EP26021_OPENROUTER_KEY", "sk-or-v1-" + "a" * 40)
        state = {"expired": False}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/api/v1/activity") and state["expired"]:
                return _resp(401, {"error": {"message": "This key has expired"}})
            if request.url.path.endswith("/models"):
                return _resp(
                    200,
                    {
                        "data": [
                            {
                                "id": "anthropic/claude-sonnet-4",
                                "name": "Claude Sonnet 4",
                                "context_length": 200000,
                                "pricing": {"prompt": "0.000003", "completion": "0.000015"},
                            }
                        ]
                    },
                )
            if request.url.path.endswith("/api/v1/activity"):
                return _resp(
                    200,
                    {
                        "data": [
                            {
                                "date": "2026-01-15",
                                "model": "anthropic/claude-sonnet-4",
                                "provider_name": "Anthropic",
                                "usage": 1.23,
                                "requests": 5,
                                "prompt_tokens": 1000,
                                "completion_tokens": 500,
                            }
                        ]
                    },
                )
            return _resp(200, {})

        provider = OpenRouterProvider(
            _openrouter_config("EP26021_OPENROUTER_KEY"),
            http_transport=httpx.MockTransport(handler),
        )

        # 1. Connect.
        assert await provider.verify_auth() is True

        # 2. Discover models — live catalog, vendor/model slug intact.
        models = await provider.list_models()
        assert any(m.id == "anthropic/claude-sonnet-4" for m in models)

        # 3. Manual sync — OpenRouter is the one provider (as of EP-26.0.1)
        #    with a real, non-empty usage import.
        page = await provider.get_usage(
            datetime(2026, 1, 15, tzinfo=UTC), datetime(2026, 1, 15, tzinfo=UTC)
        )
        assert len(page.events) == 1
        assert page.events[0].model == "anthropic/claude-sonnet-4"

        # 4. Key expires mid-lifecycle — a later sync attempt for the same
        #    connection must degrade to an honest empty page (per
        #    OpenRouterProvider.get_usage()'s own per-day fail-open
        #    behavior), never a crash, never a fabricated result.
        state["expired"] = True
        page_after_expiry = await provider.get_usage(
            datetime(2026, 1, 16, tzinfo=UTC), datetime(2026, 1, 16, tzinfo=UTC)
        )
        assert page_after_expiry.events == []

        await provider.aclose()

    @pytest.mark.asyncio
    async def test_missing_credential_still_allows_model_browsing(self) -> None:
        """OpenRouter's GET /models is unauthenticated on its own side —
        confirmed in EP-26.0.1's own research and re-pinned here as part
        of the full lifecycle."""
        provider = OpenRouterProvider(
            OpenRouterConfig(display_name="No key"),
            http_transport=httpx.MockTransport(
                lambda r: _resp(200, {"data": [{"id": "openai/gpt-4o", "name": "GPT-4o"}]})
            ),
        )
        models = await provider.list_models()
        assert len(models) > 0
        await provider.aclose()
