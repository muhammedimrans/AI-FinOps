from __future__ import annotations

from costorah._logging import redact


def test_redacts_known_sensitive_keys() -> None:
    data = {
        "api_key": "costorah_live_abc",
        "Authorization": "Bearer costorah_live_abc",
        "password": "hunter2",
        "user_prompt": "do something",
        "model_response": "the answer",
        "provider": "openai",
    }
    result = redact(data)
    assert result["api_key"] == "***REDACTED***"
    assert result["Authorization"] == "***REDACTED***"
    assert result["password"] == "***REDACTED***"
    assert result["user_prompt"] == "***REDACTED***"
    assert result["model_response"] == "***REDACTED***"
    assert result["provider"] == "openai"


def test_redacts_embedded_bearer_token_in_string() -> None:
    text = "auth failed for costorah_live_supersecrettoken123"
    result = redact(text)
    assert "supersecrettoken123" not in result
    assert "costorah_live_***REDACTED***" in result


def test_redacts_nested_structures() -> None:
    data = {"outer": {"api_key": "costorah_live_x", "safe": "ok"}}
    result = redact(data)
    assert result["outer"]["api_key"] == "***REDACTED***"
    assert result["outer"]["safe"] == "ok"


def test_redacts_lists() -> None:
    data = ["costorah_live_abcdef", "plain text"]
    result = redact(data)
    assert result[0] == "costorah_live_***REDACTED***"
    assert result[1] == "plain text"


def test_non_string_non_container_values_pass_through() -> None:
    assert redact(42) == 42
    assert redact(True) is True
    assert redact(None) is None
