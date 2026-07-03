from __future__ import annotations

import pytest

from costorah_agent.collectors._util import deterministic_request_id, env_or_config


def test_deterministic_request_id_is_stable() -> None:
    a = deterministic_request_id("openai", "1000", "1060", "gpt-4o")
    b = deterministic_request_id("openai", "1000", "1060", "gpt-4o")
    assert a == b
    assert a.startswith("agent_")


def test_deterministic_request_id_differs_for_different_input() -> None:
    a = deterministic_request_id("openai", "1000")
    b = deterministic_request_id("openai", "2000")
    assert a != b


def test_env_or_config_prefers_config_value() -> None:
    assert env_or_config({"api_key": "from-config"}, "api_key", "SOME_ENV") == "from-config"


def test_env_or_config_falls_back_to_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOME_ENV", "from-env")
    assert env_or_config({}, "api_key", "SOME_ENV") == "from-env"


def test_env_or_config_returns_none_when_neither_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SOME_ENV", raising=False)
    assert env_or_config({}, "api_key", "SOME_ENV") is None


def test_env_or_config_ignores_empty_string_config_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SOME_ENV", "from-env")
    assert env_or_config({"api_key": ""}, "api_key", "SOME_ENV") == "from-env"
