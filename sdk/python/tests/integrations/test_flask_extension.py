from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import httpx
import pytest

flask = pytest.importorskip("flask")

from flask import Blueprint, Flask, jsonify  # noqa: E402

from costorah.client import Costorah  # noqa: E402
from costorah.instrumentation import _submission  # noqa: E402
from costorah.instrumentation._submission import reset_default_client_for_tests  # noqa: E402
from costorah.instrumentation.base import ExtractedUsage  # noqa: E402
from costorah.integrations.flask import CostorahExtension  # noqa: E402


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


def test_direct_init_captures_request_context() -> None:
    captured: list[dict] = []
    client = Costorah(api_key="costorah_live_x", _transport=_echo_transport(captured))

    app = Flask(__name__)
    CostorahExtension(app, client=client, organization_id="org_1")

    @app.get("/ping")
    def ping() -> Any:
        _submission.submit(_usage())
        return jsonify({"ok": True})

    tc = app.test_client()
    response = tc.get("/ping", headers={"X-Request-Id": "custom-req-1"})

    assert response.status_code == 200
    assert response.headers["X-Costorah-Request-Id"] == "custom-req-1"

    client.flush(timeout=5)
    assert captured[0]["metadata"]["request_context"] == {
        "request_id": "custom-req-1",
        "path": "/ping",
        "method": "GET",
        "organization_id": "org_1",
    }
    client.shutdown()


def test_application_factory_pattern() -> None:
    captured: list[dict] = []
    client = Costorah(api_key="costorah_live_x", _transport=_echo_transport(captured))
    ext = CostorahExtension(client=client)

    def create_app() -> Flask:
        app = Flask(__name__)
        ext.init_app(app)

        @app.get("/ping")
        def ping() -> Any:
            _submission.submit(_usage())
            return jsonify({"ok": True})

        return app

    app = create_app()
    tc = app.test_client()
    response = tc.get("/ping")
    assert response.status_code == 200
    assert response.headers["X-Costorah-Request-Id"]
    client.shutdown()


def test_blueprint_routes_are_captured() -> None:
    captured: list[dict] = []
    client = Costorah(api_key="costorah_live_x", _transport=_echo_transport(captured))

    app = Flask(__name__)
    CostorahExtension(app, client=client)

    bp = Blueprint("api", __name__, url_prefix="/api")

    @bp.get("/items")
    def items() -> Any:
        _submission.submit(_usage())
        return jsonify([])

    app.register_blueprint(bp)

    tc = app.test_client()
    response = tc.get("/api/items", headers={"X-Request-Id": "bp-req-1"})

    assert response.status_code == 200
    client.flush(timeout=5)
    assert captured[0]["metadata"]["request_context"]["path"] == "/api/items"
    assert captured[0]["metadata"]["request_context"]["request_id"] == "bp-req-1"
    client.shutdown()


def test_multiple_flask_apps_get_isolated_request_context() -> None:
    captured_a: list[dict] = []
    captured_b: list[dict] = []
    client_a = Costorah(api_key="costorah_live_a", _transport=_echo_transport(captured_a))
    client_b = Costorah(api_key="costorah_live_b", _transport=_echo_transport(captured_b))

    app_a = Flask("app_a")
    CostorahExtension(app_a, client=client_a, organization_id="org_a")

    @app_a.get("/from-a")
    def from_a() -> Any:
        # Explicit client=, not the process-global default — see the
        # CostorahExtension docstring's note on running multiple apps
        # with distinct credentials in one process.
        _submission.submit(_usage(), client=client_a)
        return jsonify({})

    app_b = Flask("app_b")
    CostorahExtension(app_b, client=client_b, organization_id="org_b")

    @app_b.get("/from-b")
    def from_b() -> Any:
        _submission.submit(_usage(), client=client_b)
        return jsonify({})

    app_a.test_client().get("/from-a")
    app_b.test_client().get("/from-b")

    client_a.flush(timeout=5)
    client_b.flush(timeout=5)

    # Each app's own client only ever received the event captured while
    # that app's middleware held ambient context — proving isolation
    # even though costorah.instrumentation's *default* client (used when
    # no explicit client= is passed to track()) is process-global.
    assert len(captured_a) == 1
    assert captured_a[0]["metadata"]["request_context"]["organization_id"] == "org_a"
    assert len(captured_b) == 1
    assert captured_b[0]["metadata"]["request_context"]["organization_id"] == "org_b"

    client_a.shutdown()
    client_b.shutdown()


def test_extension_without_api_key_degrades_gracefully(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COSTORAH_API_KEY", raising=False)

    app = Flask(__name__)
    CostorahExtension(app)

    @app.get("/ping")
    def ping() -> Any:
        return jsonify({"ok": True})

    tc = app.test_client()
    response = tc.get("/ping")
    assert response.status_code == 200
    assert response.headers["X-Costorah-Request-Id"]
