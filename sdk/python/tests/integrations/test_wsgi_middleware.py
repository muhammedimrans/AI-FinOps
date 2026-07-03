from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone

import httpx
import pytest

from costorah.client import Costorah
from costorah.instrumentation import _submission
from costorah.instrumentation._submission import reset_default_client_for_tests
from costorah.instrumentation.base import ExtractedUsage
from costorah.integrations.wsgi import CostorahWSGIMiddleware


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


def _bare_wsgi_app(environ: dict, start_response: Callable[..., object]) -> list[bytes]:
    """A minimal hand-rolled WSGI app — no framework dependency."""
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
    start_response("200 OK", [("Content-Type", "application/json")])
    return [b"{}"]


def _call(
    app: Callable[[dict, Callable[..., object]], list[bytes]],
    path: str = "/ping",
    method: str = "GET",
    extra_environ: dict | None = None,
) -> tuple[str, dict, bytes]:
    environ = {"PATH_INFO": path, "REQUEST_METHOD": method, **(extra_environ or {})}
    captured_status: dict[str, str] = {}
    captured_headers: dict[str, dict] = {}

    def start_response(status: str, headers: list, exc_info: object = None) -> None:
        captured_status["value"] = status
        captured_headers["value"] = dict(headers)

    body = b"".join(app(environ, start_response))
    return captured_status["value"], captured_headers["value"], body


def test_wsgi_middleware_captures_request_context() -> None:
    captured: list[dict] = []
    client = Costorah(api_key="costorah_live_x", _transport=_echo_transport(captured))

    app = CostorahWSGIMiddleware(_bare_wsgi_app, client=client, organization_id="org_1")
    status, headers, _body = _call(app, extra_environ={"HTTP_X_REQUEST_ID": "custom-req-1"})

    assert status == "200 OK"
    assert headers["X-Costorah-Request-Id"] == "custom-req-1"

    client.flush(timeout=5)
    assert captured[0]["metadata"]["request_context"] == {
        "request_id": "custom-req-1",
        "path": "/ping",
        "method": "GET",
        "organization_id": "org_1",
    }
    client.shutdown()


def test_wsgi_middleware_generates_request_id_when_absent() -> None:
    captured: list[dict] = []
    client = Costorah(api_key="costorah_live_x", _transport=_echo_transport(captured))

    app = CostorahWSGIMiddleware(_bare_wsgi_app, client=client)
    _status, headers, _body = _call(app)

    assert headers["X-Costorah-Request-Id"].startswith("req_")
    client.shutdown()


def test_wsgi_middleware_without_client_degrades_gracefully(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("COSTORAH_API_KEY", raising=False)

    app = CostorahWSGIMiddleware(_bare_wsgi_app)
    status, headers, body = _call(app)

    assert status == "200 OK"
    assert headers["X-Costorah-Request-Id"]
    assert body == b"{}"
