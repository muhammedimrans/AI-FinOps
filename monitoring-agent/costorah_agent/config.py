"""
Agent configuration — loads and validates config.yaml.

Precedence (highest wins): environment variables > config file > defaults.
Environment variables are prefixed `COSTORAH_AGENT_` and use `__` as a
nesting separator, e.g. `COSTORAH_AGENT_SERVER__ENDPOINT`,
`COSTORAH_AGENT_ORGANIZATION__API_KEY` — the latter is the recommended way
to supply the API key in production (never commit it to config.yaml).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

_ENV_PREFIX = "COSTORAH_AGENT_"

_ALL_PROVIDERS = (
    "openai",
    "anthropic",
    "google",
    "azure",
    "grok",
    "openrouter",
    "ollama",
    "cohere",
    "bedrock",
    "mistral",
)

# Collectors that actually exist (Task EP-17). Enabling a provider not in
# this set is a config warning, not an error — it's forward-compatible with
# future collectors shipping without a config schema change.
IMPLEMENTED_PROVIDERS = frozenset(
    {"openai", "anthropic", "google", "azure", "openrouter", "ollama"}
)


class ServerConfig(BaseModel):
    endpoint: str = "https://api.costorah.com"
    timeout_seconds: float = Field(default=10.0, gt=0)
    verify_tls: bool = True

    @field_validator("endpoint")
    @classmethod
    def _validate_endpoint(cls, value: str) -> str:
        if not value.startswith(("https://", "http://")):
            raise ValueError("server.endpoint must start with http:// or https://")
        return value.rstrip("/")


class OrganizationConfig(BaseModel):
    api_key: str = ""

    @field_validator("api_key")
    @classmethod
    def _validate_key_shape(cls, value: str) -> str:
        # Empty is allowed at parse time (env var may supply it later, or
        # the encrypted key store may) — Agent.start() is what enforces
        # a key must be present before authenticating.
        if value and not value.startswith("costorah_live_"):
            raise ValueError("organization.api_key must start with 'costorah_live_'")
        return value


class CollectionConfig(BaseModel):
    interval_seconds: float = Field(default=5.0, gt=0)
    batch_size: int = Field(default=50, gt=0, le=1000)


class RetryConfig(BaseModel):
    backoff_seconds: list[float] = Field(
        default_factory=lambda: [1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 60.0]
    )
    max_attempts: int | None = Field(default=None, description="None = retry forever")

    @field_validator("backoff_seconds")
    @classmethod
    def _validate_backoff(cls, value: list[float]) -> list[float]:
        if not value:
            raise ValueError("retry.backoff_seconds must not be empty")
        if any(v <= 0 for v in value):
            raise ValueError("retry.backoff_seconds values must be positive")
        return value


class QueueConfig(BaseModel):
    max_memory_events: int = Field(default=10_000, gt=0)
    sqlite_path: str = "costorah-agent-queue.db"


class LoggingConfig(BaseModel):
    level: str = "INFO"
    file: str | None = None
    max_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    backup_count: int = Field(default=5, ge=0)

    @field_validator("level")
    @classmethod
    def _validate_level(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"logging.level must be a standard level, got {value!r}")
        return normalized


class ServerHttpConfig(BaseModel):
    """The agent's own local health/metrics HTTP server (not the COSTORAH server)."""

    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = Field(default=9091, gt=0, le=65535)


class AgentConfig(BaseModel):
    server: ServerConfig = Field(default_factory=ServerConfig)
    organization: OrganizationConfig = Field(default_factory=OrganizationConfig)
    collection: CollectionConfig = Field(default_factory=CollectionConfig)
    providers: dict[str, bool] = Field(default_factory=dict)
    retry: RetryConfig = Field(default_factory=RetryConfig)
    queue: QueueConfig = Field(default_factory=QueueConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    http_server: ServerHttpConfig = Field(default_factory=ServerHttpConfig)

    @model_validator(mode="after")
    def _validate_providers(self) -> AgentConfig:
        for name in self.providers:
            if name not in _ALL_PROVIDERS:
                raise ValueError(
                    f"Unknown provider {name!r} in config. Known providers: "
                    f"{sorted(_ALL_PROVIDERS)}"
                )
        return self

    def enabled_providers(self) -> list[str]:
        return [name for name, enabled in self.providers.items() if enabled]

    @classmethod
    def default(cls) -> AgentConfig:
        return cls()


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _env_overrides(prefix: str = _ENV_PREFIX) -> dict[str, Any]:
    """Build a nested dict from COSTORAH_AGENT_SECTION__FIELD=value env vars."""
    overrides: dict[str, Any] = {}
    for key, raw_value in os.environ.items():
        if not key.startswith(prefix):
            continue
        path = key[len(prefix) :].lower().split("__")
        node = overrides
        for part in path[:-1]:
            node = node.setdefault(part, {})
        node[path[-1]] = _coerce_env_value(raw_value)
    return overrides


def _coerce_env_value(raw: str) -> Any:
    lowered = raw.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw


def load_config(path: str | Path | None) -> AgentConfig:
    """
    Load and validate agent configuration.

    `path` may be None (defaults only + env overrides). File values are
    overridden by environment variables.
    """
    file_data: dict[str, Any] = {}
    if path is not None:
        config_path = Path(path)
        if config_path.exists():
            with config_path.open("r", encoding="utf-8") as fh:
                loaded = yaml.safe_load(fh) or {}
            if not isinstance(loaded, dict):
                raise ValueError(f"{config_path} must contain a YAML mapping at the top level")
            file_data = loaded

    merged = _deep_merge(file_data, _env_overrides())
    return AgentConfig.model_validate(merged)
