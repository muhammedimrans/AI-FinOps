from __future__ import annotations

from datetime import UTC, datetime

from costorah_agent.collectors.models import CollectorHealth, NormalizedUsageEvent


def test_to_ingestion_payload_includes_required_fields() -> None:
    event = NormalizedUsageEvent(
        provider="openai",
        model="gpt-4o",
        request_id="agent_abc123",
        input_tokens=10,
        output_tokens=5,
        cost=0.001,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
    )
    payload = event.to_ingestion_payload()

    assert payload["provider"] == "openai"
    assert payload["model"] == "gpt-4o"
    assert payload["request_id"] == "agent_abc123"
    assert payload["input_tokens"] == 10
    assert payload["output_tokens"] == 5
    assert payload["cost"] == 0.001
    assert payload["currency"] == "USD"
    assert payload["status"] == "success"
    assert payload["timestamp"] == "2026-01-01T00:00:00+00:00"
    assert payload["metadata"] == {}


def test_to_ingestion_payload_omits_none_optional_fields() -> None:
    event = NormalizedUsageEvent(provider="ollama", model="unknown", request_id="agent_x")
    payload = event.to_ingestion_payload()

    assert "cached_tokens" not in payload
    assert "total_tokens" not in payload
    assert "latency_ms" not in payload
    assert "region" not in payload
    assert "project_id" not in payload


def test_to_ingestion_payload_includes_present_optional_fields() -> None:
    event = NormalizedUsageEvent(
        provider="anthropic",
        model="claude",
        request_id="agent_y",
        cached_tokens=3,
        total_tokens=15,
        latency_ms=120,
        region="us-east-1",
        project_id="proj_1",
    )
    payload = event.to_ingestion_payload()

    assert payload["cached_tokens"] == 3
    assert payload["total_tokens"] == 15
    assert payload["latency_ms"] == 120
    assert payload["region"] == "us-east-1"
    assert payload["project_id"] == "proj_1"


def test_collector_health_to_dict_serializes_datetime() -> None:
    health = CollectorHealth(
        name="openai",
        enabled=True,
        healthy=True,
        detail="ok",
        last_collected_at=datetime(2026, 1, 1, tzinfo=UTC),
        events_collected_total=42,
    )
    body = health.to_dict()
    assert body["last_collected_at"] == "2026-01-01T00:00:00+00:00"
    assert body["events_collected_total"] == 42


def test_collector_health_to_dict_handles_none_datetime() -> None:
    health = CollectorHealth(name="google", enabled=True, healthy=False, detail="not implemented")
    assert health.to_dict()["last_collected_at"] is None
