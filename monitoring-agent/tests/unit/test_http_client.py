from __future__ import annotations

import httpx
import pytest

from costorah_agent.transport.http_client import HttpClient, IngestionOutcome


def _client_with_transport(transport: httpx.MockTransport) -> HttpClient:
    return HttpClient(
        endpoint="https://api.costorah.com", api_key="costorah_live_x", transport=transport
    )


async def test_send_usage_event_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer costorah_live_x"
        assert request.url.path == "/v1/ingest/usage"
        return httpx.Response(200, json={"success": True, "usage_id": "u1", "duplicate": False})

    client = _client_with_transport(httpx.MockTransport(handler))
    result = await client.send_usage_event({"provider": "openai"})
    assert result.outcome == IngestionOutcome.SUCCESS
    assert result.usage_id == "u1"
    assert result.is_retryable is False
    await client.close()


async def test_send_usage_event_duplicate() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True, "usage_id": "u1", "duplicate": True})

    client = _client_with_transport(httpx.MockTransport(handler))
    result = await client.send_usage_event({"provider": "openai"})
    assert result.outcome == IngestionOutcome.DUPLICATE
    await client.close()


@pytest.mark.parametrize("status", [401, 403])
async def test_send_usage_event_auth_failed(status: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"detail": "invalid api key"})

    client = _client_with_transport(httpx.MockTransport(handler))
    result = await client.send_usage_event({})
    assert result.outcome == IngestionOutcome.AUTH_FAILED
    assert result.detail == "invalid api key"
    assert result.is_retryable is False
    await client.close()


@pytest.mark.parametrize("status", [400, 404, 422])
async def test_send_usage_event_validation_failed(status: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"detail": "bad payload"})

    client = _client_with_transport(httpx.MockTransport(handler))
    result = await client.send_usage_event({})
    assert result.outcome == IngestionOutcome.VALIDATION_FAILED
    await client.close()


@pytest.mark.parametrize("status", [500, 502, 503])
async def test_send_usage_event_server_error_is_retryable(status: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"detail": "server error"})

    client = _client_with_transport(httpx.MockTransport(handler))
    result = await client.send_usage_event({})
    assert result.outcome == IngestionOutcome.RETRYABLE_ERROR
    assert result.is_retryable is True
    await client.close()


async def test_send_usage_event_timeout_is_retryable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out")

    client = _client_with_transport(httpx.MockTransport(handler))
    result = await client.send_usage_event({})
    assert result.outcome == IngestionOutcome.RETRYABLE_ERROR
    assert "timeout" in result.detail
    await client.close()


async def test_send_usage_event_connection_error_is_retryable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = _client_with_transport(httpx.MockTransport(handler))
    result = await client.send_usage_event({})
    assert result.outcome == IngestionOutcome.RETRYABLE_ERROR
    await client.close()


async def test_detail_truncated_and_never_echoes_full_body() -> None:
    long_detail = "x" * 2000

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"detail": long_detail})

    client = _client_with_transport(httpx.MockTransport(handler))
    result = await client.send_usage_event({})
    assert len(result.detail) == 500
    await client.close()


async def test_non_json_error_body_falls_back_to_status_line() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="not json")

    client = _client_with_transport(httpx.MockTransport(handler))
    result = await client.send_usage_event({})
    assert result.detail == "HTTP 500"
    await client.close()
