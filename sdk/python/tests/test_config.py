from __future__ import annotations

import pytest

from costorah.config import Config
from costorah.exceptions import ConfigurationError


def test_valid_config() -> None:
    config = Config(api_key="costorah_live_x")
    assert config.endpoint == "https://api.costorah.com"
    assert config.timeout == 30.0
    assert config.batch_size == 25
    assert config.flush_interval == 5.0
    assert config.max_retries == 3
    assert config.verify_tls is True


def test_missing_api_key_rejected() -> None:
    with pytest.raises(ConfigurationError, match="api_key is required"):
        Config(api_key="")


def test_api_key_without_prefix_rejected() -> None:
    with pytest.raises(ConfigurationError, match="costorah_live_"):
        Config(api_key="sk-not-costorah")


def test_endpoint_without_scheme_rejected() -> None:
    with pytest.raises(ConfigurationError, match="http"):
        Config(api_key="costorah_live_x", endpoint="api.costorah.com")


def test_endpoint_trailing_slash_stripped() -> None:
    config = Config(api_key="costorah_live_x", endpoint="https://api.costorah.com/")
    assert config.endpoint == "https://api.costorah.com"


@pytest.mark.parametrize(
    ("field", "value"),
    [("timeout", 0), ("batch_size", 0), ("flush_interval", 0), ("max_retries", -1)],
)
def test_non_positive_numeric_fields_rejected(field: str, value: float) -> None:
    with pytest.raises(ConfigurationError):
        Config(api_key="costorah_live_x", **{field: value})


def test_config_is_frozen() -> None:
    config = Config(api_key="costorah_live_x")
    with pytest.raises(AttributeError):
        config.api_key = "costorah_live_y"  # type: ignore[misc]
