from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest

celery = pytest.importorskip("celery")

from celery import Celery  # noqa: E402

from costorah.client import Costorah  # noqa: E402
from costorah.context import get_request_context  # noqa: E402
from costorah.instrumentation import _submission  # noqa: E402
from costorah.instrumentation._submission import reset_default_client_for_tests  # noqa: E402
from costorah.instrumentation.base import ExtractedUsage  # noqa: E402
from costorah.integrations.celery import CostorahCelery  # noqa: E402


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


def _make_app() -> Celery:
    app = Celery("test_app", broker="memory://", backend="cache+memory://")
    app.conf.task_always_eager = True
    app.conf.task_eager_propagates = True
    return app


def test_task_execution_gets_ambient_context() -> None:
    captured: list[dict] = []
    client = Costorah(api_key="costorah_live_x", _transport=_echo_transport(captured))
    app = _make_app()
    CostorahCelery(app, client=client, organization_id="org_1")

    seen_context: dict = {}

    @app.task(name="my.task")
    def my_task() -> None:
        seen_context.update(get_request_context() or {})
        _submission.submit(_usage())

    result = my_task.apply()
    assert result.successful()

    assert seen_context["task_name"] == "my.task"
    assert seen_context["organization_id"] == "org_1"
    assert seen_context["request_id"]

    client.flush(timeout=5)
    assert captured[0]["metadata"]["request_context"]["task_name"] == "my.task"
    client.shutdown()


def test_context_is_cleared_after_task_completes() -> None:
    app = _make_app()
    CostorahCelery(app)

    @app.task(name="cleared.task")
    def cleared_task() -> None:
        pass

    cleared_task.apply()
    assert get_request_context() is None


def test_context_isolated_across_sequential_tasks() -> None:
    app = _make_app()
    CostorahCelery(app)
    seen: list[dict] = []

    @app.task(name="task.a")
    def task_a() -> None:
        seen.append(dict(get_request_context() or {}))

    @app.task(name="task.b")
    def task_b() -> None:
        seen.append(dict(get_request_context() or {}))

    task_a.apply()
    task_b.apply()

    assert seen[0]["task_name"] == "task.a"
    assert seen[1]["task_name"] == "task.b"


def test_failing_task_still_clears_context_and_does_not_crash_signal_handlers() -> None:
    app = _make_app()
    app.conf.task_eager_propagates = False
    CostorahCelery(app)

    @app.task(name="failing.task")
    def failing_task() -> None:
        raise ValueError("boom")

    result = failing_task.apply()
    assert result.failed()
    # postrun always fires (even on failure) and clears the active-task
    # bookkeeping — no leaked ambient context for the next task.
    assert get_request_context() is None


def test_integration_without_api_key_degrades_gracefully(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("COSTORAH_API_KEY", raising=False)
    app = _make_app()
    CostorahCelery(app)  # must not raise

    @app.task(name="noop.task")
    def noop_task() -> str:
        return "ok"

    result = noop_task.apply()
    assert result.successful()
    assert result.result == "ok"
