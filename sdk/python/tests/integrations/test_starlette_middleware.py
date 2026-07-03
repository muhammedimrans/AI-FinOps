from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest

starlette = pytest.importorskip("starlette")

from starlette.applications import Starlette  # noqa: E402
from starlette.responses import JSONResponse  # noqa: E402
from starlette.routing import Route  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from costorah.client import Costorah  # noqa: E402
from costorah.instrumentation import _submission  # noqa: E402
from costorah.instrumentation._submission import reset_default_client_for_tests  # noqa: E402
from costorah.instrumentation.base import ExtractedUsage  # noqa: E402
from costorah.integrations import fastapi as fastapi_integration  # noqa: E402
from costorah.integrations.starlette import CostorahMiddleware  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_state() -> None:
    reset_default_client_for_tests()
    yield
    reset_default_client_for_tests()


def test_starlette_middleware_is_the_fastapi_middleware_class() -> None:
    """Documents the deliberate reuse — no duplicate implementation."""
    assert CostorahMiddleware is fastapi_integration.CostorahMiddleware


def test_starlette_middleware_works_on_a_bare_starlette_app() -> None:
    captured: list[dict] = []

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

    client = Costorah(api_key="costorah_live_x", _transport=httpx.MockTransport(handler))

    async def ping(request: object) -> JSONResponse:
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
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/ping", ping)])
    app.add_middleware(CostorahMiddleware, client=client, organization_id="org_1")

    tc = TestClient(app)
    response = tc.get("/ping", headers={"X-Request-Id": "starlette-req-1"})

    assert response.status_code == 200
    assert response.headers["x-costorah-request-id"] == "starlette-req-1"

    client.flush(timeout=5)
    assert captured[0]["metadata"]["request_context"] == {
        "request_id": "starlette-req-1",
        "path": "/ping",
        "method": "GET",
        "organization_id": "org_1",
    }
    client.shutdown()
