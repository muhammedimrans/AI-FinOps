from __future__ import annotations

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from costorah_agent.config import AgentConfig, OrganizationConfig, RetryConfig, load_config


def test_default_config_is_valid() -> None:
    config = AgentConfig.default()
    assert config.server.endpoint == "https://api.costorah.com"
    assert config.http_server.host == "127.0.0.1"
    assert config.queue.max_memory_events == 10_000


def test_organization_api_key_must_have_costorah_prefix() -> None:
    with pytest.raises(ValidationError):
        OrganizationConfig(api_key="sk-not-costorah")


def test_organization_api_key_empty_is_allowed() -> None:
    assert OrganizationConfig(api_key="").api_key == ""


def test_server_endpoint_must_have_scheme() -> None:
    with pytest.raises(ValidationError):
        AgentConfig.model_validate({"server": {"endpoint": "api.costorah.com"}})


def test_server_endpoint_trailing_slash_stripped() -> None:
    config = AgentConfig.model_validate({"server": {"endpoint": "https://api.costorah.com/"}})
    assert config.server.endpoint == "https://api.costorah.com"


def test_retry_backoff_seconds_must_not_be_empty() -> None:
    with pytest.raises(ValidationError, match="must not be empty"):
        RetryConfig(backoff_seconds=[])


def test_retry_backoff_seconds_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        RetryConfig(backoff_seconds=[1.0, -2.0])


def test_unknown_provider_name_rejected() -> None:
    with pytest.raises(ValidationError, match="Unknown provider"):
        AgentConfig.model_validate({"providers": {"not_a_real_provider": True}})


def test_enabled_providers_filters_false_values() -> None:
    config = AgentConfig.model_validate(
        {"providers": {"openai": True, "anthropic": False, "ollama": True}}
    )
    assert sorted(config.enabled_providers()) == ["ollama", "openai"]


def test_logging_level_normalized_to_uppercase() -> None:
    config = AgentConfig.model_validate({"logging": {"level": "debug"}})
    assert config.logging.level == "DEBUG"


def test_logging_level_rejects_unknown_value() -> None:
    with pytest.raises(ValidationError):
        AgentConfig.model_validate({"logging": {"level": "verbose"}})


def test_load_config_from_yaml_file(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "server:\n  endpoint: https://custom.example.com\ncollection:\n  interval_seconds: 30\n"
    )
    config = load_config(config_file)
    assert config.server.endpoint == "https://custom.example.com"
    assert config.collection.interval_seconds == 30


def test_load_config_missing_file_uses_defaults(tmp_path: Path) -> None:
    config = load_config(tmp_path / "does-not-exist.yaml")
    assert config.server.endpoint == "https://api.costorah.com"


def test_load_config_none_path_uses_defaults_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COSTORAH_AGENT_SERVER__ENDPOINT", "https://env.example.com")
    config = load_config(None)
    assert config.server.endpoint == "https://env.example.com"


def test_env_override_beats_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("server:\n  endpoint: https://file.example.com\n")
    monkeypatch.setenv("COSTORAH_AGENT_SERVER__ENDPOINT", "https://env.example.com")
    config = load_config(config_file)
    assert config.server.endpoint == "https://env.example.com"


def test_env_override_coerces_bool_and_int(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COSTORAH_AGENT_SERVER__VERIFY_TLS", "false")
    monkeypatch.setenv("COSTORAH_AGENT_QUEUE__MAX_MEMORY_EVENTS", "500")
    config = load_config(None)
    assert config.server.verify_tls is False
    assert config.queue.max_memory_events == 500


def test_env_override_api_key(monkeypatch: pytest.MonkeyPatch, valid_api_key: str) -> None:
    monkeypatch.setenv("COSTORAH_AGENT_ORGANIZATION__API_KEY", valid_api_key)
    config = load_config(None)
    assert config.organization.api_key == valid_api_key


def test_load_config_non_mapping_yaml_rejected(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("- just\n- a\n- list\n")
    with pytest.raises(ValueError, match="mapping"):
        load_config(config_file)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("COSTORAH_AGENT_"):
            monkeypatch.delenv(key, raising=False)
