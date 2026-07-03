from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from costorah import Costorah
from costorah.exceptions import ValidationError


def _echo_transport(captured: list[dict]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        import json

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


def test_track_builds_expected_minimal_payload() -> None:
    captured: list[dict] = []
    client = Costorah(api_key="costorah_live_x", _transport=_echo_transport(captured))
    client.track(provider="openai", model="gpt-4.1", cost=0.041)
    client.close()

    payload = captured[0]
    assert payload["provider"] == "openai"
    assert payload["model"] == "gpt-4.1"
    assert payload["cost"] == 0.041
    assert payload["currency"] == "USD"
    assert payload["status"] == "success"
    assert payload["input_tokens"] == 0
    assert payload["output_tokens"] == 0
    assert "cached_tokens" not in payload
    assert "total_tokens" not in payload
    assert "latency_ms" not in payload
    assert "region" not in payload
    assert "project_id" not in payload
    assert "timestamp" not in payload
    assert payload["metadata"] == {}
    assert payload["request_id"].startswith("sdk_py_")


def test_track_includes_optional_fields_when_provided() -> None:
    captured: list[dict] = []
    client = Costorah(api_key="costorah_live_x", _transport=_echo_transport(captured))
    client.track(
        provider="anthropic",
        model="claude-sonnet-4",
        input_tokens=200,
        output_tokens=80,
        cached_tokens=10,
        total_tokens=280,
        cost=0.012,
        latency_ms=410,
        region="us-east-1",
        project_id="proj_1",
        request_id="my-custom-id",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        metadata={"foo": "bar"},
    )
    client.close()

    payload = captured[0]
    assert payload["cached_tokens"] == 10
    assert payload["total_tokens"] == 280
    assert payload["latency_ms"] == 410
    assert payload["region"] == "us-east-1"
    assert payload["project_id"] == "proj_1"
    assert payload["request_id"] == "my-custom-id"
    assert payload["timestamp"] == "2026-01-01T00:00:00+00:00"
    assert payload["metadata"] == {"foo": "bar"}


def test_track_normalizes_provider_case_and_whitespace() -> None:
    captured: list[dict] = []
    client = Costorah(api_key="costorah_live_x", _transport=_echo_transport(captured))
    client.track(provider="  OpenAI  ", model="gpt-4.1", cost=0.01)
    client.close()
    assert captured[0]["provider"] == "openai"


def test_track_rejects_unsupported_provider() -> None:
    client = Costorah(
        api_key="costorah_live_x", _transport=httpx.MockTransport(lambda r: httpx.Response(200))
    )
    with pytest.raises(ValidationError, match="Unsupported provider"):
        client.track(provider="not-a-real-provider", model="x", cost=0.0)
    client.close()


def test_track_rejects_blank_model() -> None:
    client = Costorah(
        api_key="costorah_live_x", _transport=httpx.MockTransport(lambda r: httpx.Response(200))
    )
    with pytest.raises(ValidationError, match="model must not be blank"):
        client.track(provider="openai", model="   ", cost=0.0)
    client.close()


@pytest.mark.parametrize("field", ["input_tokens", "output_tokens"])
def test_track_rejects_negative_tokens(field: str) -> None:
    client = Costorah(
        api_key="costorah_live_x", _transport=httpx.MockTransport(lambda r: httpx.Response(200))
    )
    with pytest.raises(ValidationError):
        client.track(provider="openai", model="gpt-4.1", cost=0.0, **{field: -1})
    client.close()


def test_track_rejects_negative_cost() -> None:
    client = Costorah(
        api_key="costorah_live_x", _transport=httpx.MockTransport(lambda r: httpx.Response(200))
    )
    with pytest.raises(ValidationError, match="cost must be"):
        client.track(provider="openai", model="gpt-4.1", cost=-1.0)
    client.close()


def test_track_rejects_cached_tokens_exceeding_input_tokens() -> None:
    client = Costorah(
        api_key="costorah_live_x", _transport=httpx.MockTransport(lambda r: httpx.Response(200))
    )
    with pytest.raises(ValidationError, match="cached_tokens"):
        client.track(provider="openai", model="gpt-4.1", cost=0.0, input_tokens=5, cached_tokens=10)
    client.close()


def test_track_rejects_total_tokens_mismatch() -> None:
    client = Costorah(
        api_key="costorah_live_x", _transport=httpx.MockTransport(lambda r: httpx.Response(200))
    )
    with pytest.raises(ValidationError, match="total_tokens"):
        client.track(
            provider="openai",
            model="gpt-4.1",
            cost=0.0,
            input_tokens=5,
            output_tokens=5,
            total_tokens=100,
        )
    client.close()


def test_client_used_as_context_manager() -> None:
    captured: list[dict] = []
    with Costorah(api_key="costorah_live_x", _transport=_echo_transport(captured)) as client:
        result = client.track(provider="openai", model="gpt-4.1", cost=0.01)
        assert result.usage_id == "u1"
