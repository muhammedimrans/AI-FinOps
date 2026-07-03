from __future__ import annotations

from costorah_agent.logging_setup import redact_sensitive_fields


def test_redacts_known_sensitive_key_names() -> None:
    event = {
        "api_key": "costorah_live_abc",
        "Authorization": "Bearer costorah_live_abc",
        "password": "hunter2",
        "user_prompt": "do something",
        "model_response": "here is the answer",
        "event": "some_event",
    }
    result = redact_sensitive_fields(None, "info", dict(event))
    assert result["api_key"] == "***REDACTED***"
    assert result["Authorization"] == "***REDACTED***"
    assert result["password"] == "***REDACTED***"
    assert result["user_prompt"] == "***REDACTED***"
    assert result["model_response"] == "***REDACTED***"
    assert result["event"] == "some_event"  # untouched, not a sensitive key


def test_redacts_embedded_bearer_token_in_arbitrary_field() -> None:
    event = {"detail": "auth failed for costorah_live_supersecrettoken123"}
    result = redact_sensitive_fields(None, "info", event)
    assert "supersecrettoken123" not in result["detail"]
    assert "costorah_live_***REDACTED***" in result["detail"]


def test_leaves_non_sensitive_values_untouched() -> None:
    event = {"queue_size": 5, "provider": "openai", "healthy": True}
    result = redact_sensitive_fields(None, "info", dict(event))
    assert result == event


def test_case_insensitive_key_matching() -> None:
    event = {"API_KEY": "costorah_live_x", "ApiKey": "costorah_live_y"}
    result = redact_sensitive_fields(None, "info", event)
    assert result["API_KEY"] == "***REDACTED***"
    assert result["ApiKey"] == "***REDACTED***"


def test_non_string_values_pass_through_key_redaction_only() -> None:
    event = {"queue_size": 42, "secret_count": 3}
    result = redact_sensitive_fields(None, "info", dict(event))
    assert result["queue_size"] == 42
    assert result["secret_count"] == "***REDACTED***"
