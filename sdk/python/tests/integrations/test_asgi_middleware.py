from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import httpx
import pytest

from costorah.client import Costorah
from costorah.instrumentation import _submission
from costorah.instrumentation._submission import reset_default_client_for_tests
from costorah.instrumentation.base import ExtractedUsage
from costorah.integrations.asgi import CostorahASGIMiddleware


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


async def _bare_asgi_app(scope: dict, receive: object, send: object) -> None:
    """A minimal hand-rolled ASGI 3 app — no framework dependency."""
    if scope["type"] != "http":
        return
    _submission.submit(
        ExtractedUsage(
            provider="openai",
            model="gpt-4o",
            input_tokens=1,
            output_tokens=1,
            cost=0.0,
            request_id="r1",
            timestamp=datetime.now(timezone.utc),
        )
    )
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"{}"})


def _run_asgi(app: object, scope: dict) -> tuple[int, list[tuple[bytes, bytes]]]:
    async def receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    messages: list[dict] = []

    async def send(message: dict) -> None:
        messages.append(message)

    asyncio.run(app(scope, receive, send))
    start = next(m for m in messages if m["type"] == "http.response.start")
    return start["status"], start["headers"]


def _http_scope(
    path: str = "/ping", method: str = "GET", headers: list | None = None
) -> dict:
    return {
        "type": "http",
        "path": path,
        "method": method,
        "headers": headers or [],
    }


def test_asgi_middleware_captures_request_context() -> None:
    captured: list[dict] = []
    client = Costorah(api_key="costorah_live_x", _transport=_echo_transport(captured))

    app = CostorahASGIMiddleware(_bare_asgi_app, client=client, organization_id="org_1")
    status, headers = _run_asgi(
        app, _http_scope(headers=[(b"x-request-id", b"custom-req-1")])
    )

    assert status == 200
    header_map = dict(headers)
    assert header_map[b"x-costorah-request-id"] == b"custom-req-1"

    client.flush(timeout=5)
    assert captured[0]["metadata"]["request_context"] == {
        "request_id": "custom-req-1",
        "path": "/ping",
        "method": "GET",
        "organization_id": "org_1",
    }
    client.shutdown()


def test_asgi_middleware_generates_request_id_when_absent() -> None:
    captured: list[dict] = []
    client = Costorah(api_key="costorah_live_x", _transport=_echo_transport(captured))

    app = CostorahASGIMiddleware(_bare_asgi_app, client=client)
    _status, headers = _run_asgi(app, _http_scope())

    header_map = dict(headers)
    assert header_map[b"x-costorah-request-id"].startswith(b"req_")
    client.shutdown()


def test_asgi_middleware_passes_through_non_http_scopes() -> None:
    """Lifespan/websocket scopes must not be touched — this must not
    crash even though _bare_asgi_app only handles 'http'."""

    async def receive() -> dict:
        return {"type": "lifespan.startup"}

    async def send(_message: dict) -> None:
        pass

    app = CostorahASGIMiddleware(_bare_asgi_app)
    asyncio.run(app({"type": "lifespan"}, receive, send))  # must not raise
