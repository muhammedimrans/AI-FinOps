from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import httpx
import pytest

django = pytest.importorskip("django")

from django.conf import settings  # noqa: E402

if not settings.configured:
    settings.configure(
        DEBUG=True,
        ALLOWED_HOSTS=["testserver"],
        SECRET_KEY="test-secret-key",
        DATABASES={},
        USE_TZ=True,
    )
    django.setup()

from django.test import RequestFactory  # noqa: E402

import costorah.integrations.django.middleware as django_middleware  # noqa: E402
from costorah.client import Costorah  # noqa: E402
from costorah.instrumentation import _submission  # noqa: E402
from costorah.instrumentation._submission import reset_default_client_for_tests  # noqa: E402
from costorah.instrumentation.base import ExtractedUsage  # noqa: E402
from costorah.integrations.django import CostorahMiddleware  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_state() -> None:
    reset_default_client_for_tests()
    yield
    reset_default_client_for_tests()


def _echo_transport(captured: list[dict]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "success": True,
                "usage_id": "u1",
                "request_id": captured[-1]["request_id"],
                "processed_at": "2026-01-01T00:00:00Z",
                "duplicate": False,
            },
        )

    return httpx.MockTransport(handler)


def _usage() -> ExtractedUsage:
    return ExtractedUsage(
        provider="openai",
        model="gpt-4o",
        input_tokens=1,
        output_tokens=1,
        cost=0.0,
        request_id="r1",
        timestamp=datetime.now(timezone.utc),
    )


class _FakeUser:
    def __init__(self, pk: int, *, is_authenticated: bool) -> None:
        self.pk = pk
        self.is_authenticated = is_authenticated


def _patch_client(monkeypatch: pytest.MonkeyPatch, client: Costorah, org_id: str | None) -> None:
    monkeypatch.setattr(django_middleware, "_build_client_from_settings", lambda: client)
    monkeypatch.setattr(
        django_middleware, "_organization_id_from_settings", lambda: org_id
    )


def test_sync_middleware_captures_request_context(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[dict] = []
    client = Costorah(api_key="costorah_live_x", _transport=_echo_transport(captured))
    _patch_client(monkeypatch, client, "org_1")

    def get_response(request: object) -> object:
        _submission.submit(_usage())
        response: dict[str, str] = {}
        return response

    middleware = CostorahMiddleware(get_response)
    assert middleware._is_async_middleware is False

    request = RequestFactory().get("/ping", HTTP_X_REQUEST_ID="custom-req-1")
    request.user = _FakeUser(42, is_authenticated=True)

    response = middleware(request)
    assert response["X-Costorah-Request-Id"] == "custom-req-1"

    client.flush(timeout=5)
    assert captured[0]["metadata"]["request_context"] == {
        "request_id": "custom-req-1",
        "path": "/ping",
        "method": "GET",
        "organization_id": "org_1",
        "user_id": "42",
    }
    client.shutdown()


def test_sync_middleware_omits_user_id_when_anonymous(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[dict] = []
    client = Costorah(api_key="costorah_live_x", _transport=_echo_transport(captured))
    _patch_client(monkeypatch, client, None)

    def get_response(request: object) -> object:
        _submission.submit(_usage())
        return {}

    middleware = CostorahMiddleware(get_response)
    request = RequestFactory().get("/ping")
    request.user = _FakeUser(0, is_authenticated=False)

    middleware(request)
    client.flush(timeout=5)
    assert "user_id" not in captured[0]["metadata"]["request_context"]
    assert "organization_id" not in captured[0]["metadata"]["request_context"]
    client.shutdown()


def test_sync_middleware_without_user_attribute_does_not_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Apps without AuthenticationMiddleware installed have no
    request.user at all — must degrade gracefully, not raise."""
    captured: list[dict] = []
    client = Costorah(api_key="costorah_live_x", _transport=_echo_transport(captured))
    _patch_client(monkeypatch, client, None)

    def get_response(request: object) -> object:
        return {}

    middleware = CostorahMiddleware(get_response)
    request = RequestFactory().get("/ping")  # no .user set

    response = middleware(request)
    assert response["X-Costorah-Request-Id"]
    client.shutdown()


def test_async_middleware_captures_request_context(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[dict] = []
    client = Costorah(api_key="costorah_live_x", _transport=_echo_transport(captured))
    _patch_client(monkeypatch, client, "org_async")

    async def get_response(request: object) -> object:
        _submission.submit(_usage())
        return {}

    middleware = CostorahMiddleware(get_response)
    assert middleware._is_async_middleware is True

    request = RequestFactory().get("/ping", HTTP_X_REQUEST_ID="async-req-1")
    response = asyncio.run(middleware(request))

    assert response["X-Costorah-Request-Id"] == "async-req-1"
    client.flush(timeout=5)
    assert captured[0]["metadata"]["request_context"]["organization_id"] == "org_async"
    client.shutdown()


def test_middleware_reraises_and_logs_on_view_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    client = Costorah(api_key="costorah_live_x", _transport=_echo_transport([]))
    _patch_client(monkeypatch, client, None)

    def get_response(request: object) -> object:
        raise ValueError("boom")

    middleware = CostorahMiddleware(get_response)
    request = RequestFactory().get("/ping")

    with pytest.raises(ValueError, match="boom"):
        middleware(request)
    client.shutdown()


def test_middleware_without_configured_client_degrades_gracefully(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(django_middleware, "_build_client_from_settings", lambda: None)
    monkeypatch.setattr(django_middleware, "_organization_id_from_settings", lambda: None)

    def get_response(request: object) -> object:
        return {}

    middleware = CostorahMiddleware(get_response)
    request = RequestFactory().get("/ping")
    response = middleware(request)
    assert response["X-Costorah-Request-Id"]
