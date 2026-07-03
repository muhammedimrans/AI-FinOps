from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from costorah._http import HttpTransport
from costorah.config import Config
from costorah.exceptions import (
    AuthenticationError,
    NetworkError,
    RateLimitError,
    ServerError,
    ValidationError,
)


def _transport(config: Config, handler: Callable[[httpx.Request], httpx.Response]) -> HttpTransport:
    return HttpTransport(config, transport=httpx.MockTransport(handler))


def test_successful_post() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer costorah_live_x"
        assert request.url.path == "/v1/ingest/usage"
        return httpx.Response(
            200,
            json={
                "success": True,
                "usage_id": "u1",
                "request_id": "r1",
                "processed_at": "2026-01-01T00:00:00Z",
                "duplicate": False,
            },
        )

    config = Config(api_key="costorah_live_x")
    transport = _transport(config, handler)
    body = transport.post_usage_event({"provider": "openai"})
    assert body["usage_id"] == "u1"
    transport.close()


@pytest.mark.parametrize("status", [401, 403])
def test_auth_failure_raises_immediately_no_retry(status: int) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(status, json={"detail": "invalid key"})

    config = Config(api_key="costorah_live_x", max_retries=3)
    transport = _transport(config, handler)
    with pytest.raises(AuthenticationError) as exc_info:
        transport.post_usage_event({})
    assert exc_info.value.status_code == status
    assert calls["n"] == 1  # not retried
    transport.close()


@pytest.mark.parametrize("status", [400, 404, 422])
def test_validation_failure_raises_immediately_no_retry(status: int) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(status, json={"detail": "bad payload"})

    config = Config(api_key="costorah_live_x", max_retries=3)
    transport = _transport(config, handler)
    with pytest.raises(ValidationError):
        transport.post_usage_event({})
    assert calls["n"] == 1
    transport.close()


def test_server_error_retries_then_succeeds() -> None:
    responses = iter(
        [
            httpx.Response(503, json={"detail": "down"}),
            httpx.Response(503, json={"detail": "down"}),
            httpx.Response(
                200,
                json={
                    "success": True,
                    "usage_id": "u1",
                    "request_id": "r1",
                    "processed_at": "2026-01-01T00:00:00Z",
                    "duplicate": False,
                },
            ),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return next(responses)

    config = Config(api_key="costorah_live_x", max_retries=5)
    transport = _transport(config, handler)
    import time

    start = time.monotonic()
    body = transport.post_usage_event({})
    elapsed = time.monotonic() - start
    assert body["usage_id"] == "u1"
    assert elapsed >= 1.0 + 2.0 - 0.2  # first two backoff delays (1s, 2s), generous tolerance
    transport.close()


def test_server_error_exhausts_retries_and_raises() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500, json={"detail": "boom"})

    config = Config(api_key="costorah_live_x", max_retries=2)
    transport = _transport(config, handler)
    with pytest.raises(ServerError):
        transport.post_usage_event({})
    assert calls["n"] == 3  # initial attempt + 2 retries
    transport.close()


def test_rate_limit_retries_honoring_retry_after() -> None:
    responses = iter(
        [
            httpx.Response(429, headers={"Retry-After": "0.2"}, json={"detail": "slow down"}),
            httpx.Response(
                200,
                json={
                    "success": True,
                    "usage_id": "u1",
                    "request_id": "r1",
                    "processed_at": "2026-01-01T00:00:00Z",
                    "duplicate": False,
                },
            ),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return next(responses)

    config = Config(api_key="costorah_live_x", max_retries=3)
    transport = _transport(config, handler)
    import time

    start = time.monotonic()
    transport.post_usage_event({})
    elapsed = time.monotonic() - start
    assert 0.15 <= elapsed < 1.0  # honored the short Retry-After, not the 1s default backoff
    transport.close()


def test_rate_limit_exhausts_retries_raises_rate_limit_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "0.01"}, json={"detail": "slow down"})

    config = Config(api_key="costorah_live_x", max_retries=1)
    transport = _transport(config, handler)
    with pytest.raises(RateLimitError) as exc_info:
        transport.post_usage_event({})
    assert exc_info.value.retry_after == 0.01
    transport.close()


def test_timeout_is_retried_as_network_error() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise httpx.TimeoutException("timed out")

    config = Config(api_key="costorah_live_x", max_retries=1)
    transport = _transport(config, handler)
    with pytest.raises(NetworkError):
        transport.post_usage_event({})
    assert calls["n"] == 2
    transport.close()


def test_connection_error_is_retried_as_network_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    config = Config(api_key="costorah_live_x", max_retries=0)
    transport = _transport(config, handler)
    with pytest.raises(NetworkError):
        transport.post_usage_event({})
    transport.close()


def test_detail_truncated_and_never_echoes_full_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"detail": "x" * 2000})

    config = Config(api_key="costorah_live_x")
    transport = _transport(config, handler)
    with pytest.raises(ValidationError) as exc_info:
        transport.post_usage_event({})
    assert len(str(exc_info.value)) == 500
    transport.close()


def test_context_manager_closes_transport() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "success": True,
                "usage_id": "u1",
                "request_id": "r1",
                "processed_at": "2026-01-01T00:00:00Z",
                "duplicate": False,
            },
        )

    config = Config(api_key="costorah_live_x")
    with _transport(config, handler) as transport:
        transport.post_usage_event({})
