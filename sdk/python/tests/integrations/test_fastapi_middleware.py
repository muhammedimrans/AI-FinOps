from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest

fastapi = pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from costorah.client import Costorah  # noqa: E402
from costorah.instrumentation import _submission  # noqa: E402
from costorah.instrumentation._submission import reset_default_client_for_tests  # noqa: E402
from costorah.instrumentation.base import ExtractedUsage  # noqa: E402
from costorah.integrations.fastapi import CostorahMiddleware  # noqa: E402


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


def test_middleware_sets_default_client_and_captures_request_context() -> None:
    captured: list[dict] = []
    client = Costorah(api_key="costorah_live_x", _transport=_echo_transport(captured))

    app = FastAPI()
    app.add_middleware(CostorahMiddleware, client=client, organization_id="org_1")

    @app.get("/ping")
    def ping() -> dict:
        _submission.submit(_usage())
        return {"ok": True}

    tc = TestClient(app)
    response = tc.get("/ping", headers={"X-Request-Id": "custom-req-1"})

    assert response.status_code == 200
    assert response.headers["x-costorah-request-id"] == "custom-req-1"

    client.flush(timeout=5)
    assert len(captured) == 1
    context = captured[0]["metadata"]["request_context"]
    assert context == {
        "request_id": "custom-req-1",
        "path": "/ping",
        "method": "GET",
        "organization_id": "org_1",
    }
    client.shutdown()


def test_middleware_generates_a_request_id_when_absent() -> None:
    captured: list[dict] = []
    client = Costorah(api_key="costorah_live_x", _transport=_echo_transport(captured))

    app = FastAPI()
    app.add_middleware(CostorahMiddleware, client=client)

    @app.get("/ping")
    def ping() -> dict:
        _submission.submit(_usage())
        return {"ok": True}

    tc = TestClient(app)
    response = tc.get("/ping")

    assert response.headers["x-costorah-request-id"].startswith("req_")
    client.flush(timeout=5)
    assert captured[0]["metadata"]["request_context"]["request_id"].startswith("req_")
    client.shutdown()


def test_request_context_does_not_leak_across_requests() -> None:
    captured: list[dict] = []
    client = Costorah(api_key="costorah_live_x", _transport=_echo_transport(captured))

    app = FastAPI()
    app.add_middleware(CostorahMiddleware, client=client)

    @app.get("/a")
    def a() -> dict:
        _submission.submit(_usage())
        return {}

    @app.get("/b")
    def b() -> dict:
        _submission.submit(_usage())
        return {}

    tc = TestClient(app)
    tc.get("/a", headers={"X-Request-Id": "req-a"})
    tc.get("/b", headers={"X-Request-Id": "req-b"})

    client.flush(timeout=5)
    assert captured[0]["metadata"]["request_context"]["path"] == "/a"
    assert captured[1]["metadata"]["request_context"]["path"] == "/b"
    client.shutdown()


def test_middleware_without_client_or_api_key_degrades_gracefully(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No COSTORAH_API_KEY, no explicit client — the middleware must not
    crash the app; requests should still succeed."""
    monkeypatch.delenv("COSTORAH_API_KEY", raising=False)

    app = FastAPI()
    app.add_middleware(CostorahMiddleware)

    @app.get("/ping")
    def ping() -> dict:
        return {"ok": True}

    tc = TestClient(app)
    response = tc.get("/ping")
    assert response.status_code == 200
    assert response.headers["x-costorah-request-id"]


def test_middleware_auto_inits_from_env_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COSTORAH_API_KEY", "costorah_live_env")


    captured_kwargs: dict[str, object] = {}
    real_init = Costorah.__init__

    def spy_init(self: object, *args: object, **kwargs: object) -> None:
        captured_kwargs.update(kwargs)
        kwargs["_transport"] = httpx.MockTransport(
            lambda r: httpx.Response(
                200,
                json={
                    "success": True,
                    "usage_id": "u1",
                    "request_id": "r1",
                    "processed_at": "2026-01-01T00:00:00Z",
                    "duplicate": False,
                },
            )
        )
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(Costorah, "__init__", spy_init)

    app = FastAPI()
    app.add_middleware(CostorahMiddleware)
    tc = TestClient(app)
    tc.get("/does-not-exist")  # triggers app startup / middleware construction

    assert captured_kwargs.get("api_key") == "costorah_live_env"
