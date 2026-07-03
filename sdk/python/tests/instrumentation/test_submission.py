from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from costorah.instrumentation import _submission
from costorah.instrumentation.base import ExtractedUsage


def _usage(**overrides: object) -> ExtractedUsage:
    defaults: dict[str, object] = dict(
        provider="openai",
        model="gpt-4o",
        input_tokens=10,
        output_tokens=5,
        cost=0.01,
        request_id="req-1",
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return ExtractedUsage(**defaults)  # type: ignore[arg-type]


def test_submit_returns_false_with_no_client_and_no_env_key() -> None:
    assert _submission.submit(_usage()) is False


def test_submit_uses_explicit_client(monkeypatch: pytest.MonkeyPatch) -> None:
    from costorah.client import Costorah

    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "success": True,
                "usage_id": "u1",
                "request_id": "req-1",
                "processed_at": "2026-01-01T00:00:00Z",
                "duplicate": False,
            },
        )

    client = Costorah(api_key="costorah_live_x", _transport=httpx.MockTransport(handler))
    ok = _submission.submit(_usage(), client=client)
    assert ok is True
    assert len(requests) == 1
    client.close()


def test_submit_builds_lazy_client_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COSTORAH_API_KEY", "costorah_live_env")

    import costorah.client as client_module

    captured_kwargs: dict[str, object] = {}
    real_init = client_module.Costorah.__init__

    def spy_init(self: object, *args: object, **kwargs: object) -> None:
        captured_kwargs.update(kwargs)
        # Force a transport that always succeeds so submit() doesn't hit the network.
        kwargs["_transport"] = httpx.MockTransport(
            lambda r: httpx.Response(
                200,
                json={
                    "success": True,
                    "usage_id": "u1",
                    "request_id": "req-1",
                    "processed_at": "2026-01-01T00:00:00Z",
                    "duplicate": False,
                },
            )
        )
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(client_module.Costorah, "__init__", spy_init)

    ok = _submission.submit(_usage())
    assert ok is True
    assert captured_kwargs["api_key"] == "costorah_live_env"


def test_submit_caches_default_client_across_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COSTORAH_API_KEY", "costorah_live_env")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "success": True,
                "usage_id": "u1",
                "request_id": "req-1",
                "processed_at": "2026-01-01T00:00:00Z",
                "duplicate": False,
            },
        )

    import costorah.client as client_module

    real_init = client_module.Costorah.__init__
    init_calls = {"n": 0}

    def spy_init(self: object, *args: object, **kwargs: object) -> None:
        init_calls["n"] += 1
        kwargs["_transport"] = httpx.MockTransport(handler)
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(client_module.Costorah, "__init__", spy_init)

    _submission.submit(_usage())
    _submission.submit(_usage())
    assert init_calls["n"] == 1  # built once, reused


def test_submit_returns_false_on_costorah_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from costorah.client import Costorah

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "invalid key"})

    client = Costorah(api_key="costorah_live_x", _transport=httpx.MockTransport(handler))
    ok = _submission.submit(_usage(), client=client)
    assert ok is False
    client.close()


def test_submit_never_raises_on_client_construction_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COSTORAH_API_KEY", "not-a-valid-prefix")
    ok = _submission.submit(_usage())
    assert ok is False
