from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The sentinel value used when APP_SECRET_KEY is not explicitly set.
# Safe for development/testing; rejected by the model validator in production.
_DEV_SECRET = "CHANGE-ME-IN-PRODUCTION-THIS-IS-NOT-SECURE!!"  # noqa: S105


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    All fields map directly to the variable names in .env.example.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── Application ──────────────────────────────────────────────────────────
    app_env: Literal["development", "staging", "production", "testing"] = "development"
    app_debug: bool = False
    app_secret_key: str = Field(default=_DEV_SECRET, min_length=32)

    @model_validator(mode="after")
    def _enforce_secret_in_production(self) -> "Settings":
        if self.app_env == "production" and self.app_secret_key == _DEV_SECRET:
            raise ValueError(
                "APP_SECRET_KEY must be set to a secure random value in production."
            )
        return self
    app_log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # ─── API server ───────────────────────────────────────────────────────────
    api_host: str = "0.0.0.0"
    api_port: int = Field(default=8000, ge=1, le=65535)
    api_workers: int = Field(default=1, ge=1)
    api_reload: bool = False
    api_cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # ─── PostgreSQL ───────────────────────────────────────────────────────────
    postgres_host: str = "localhost"
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    postgres_db: str = "aifinops"
    postgres_user: str = "aifinops"
    postgres_password: str = "aifinops_dev_password"

    @computed_field  # type: ignore[misc]
    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field  # type: ignore[misc]
    @property
    def database_url_sync(self) -> str:
        """Synchronous URL used by Alembic migrations."""
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # ─── ClickHouse ───────────────────────────────────────────────────────────
    clickhouse_host: str = "localhost"
    clickhouse_port: int = Field(default=8123, ge=1, le=65535)
    clickhouse_db: str = "aifinops"
    clickhouse_user: str = "aifinops"
    clickhouse_password: str = "aifinops_dev_password"

    @computed_field  # type: ignore[misc]
    @property
    def clickhouse_url(self) -> str:
        return f"http://{self.clickhouse_host}:{self.clickhouse_port}"

    # ─── Redis ────────────────────────────────────────────────────────────────
    redis_host: str = "localhost"
    redis_port: int = Field(default=6379, ge=1, le=65535)
    redis_db: int = Field(default=0, ge=0, le=15)
    redis_password: str = ""

    @computed_field  # type: ignore[misc]
    @property
    def redis_url(self) -> str:
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    # ─── Observability ────────────────────────────────────────────────────────
    otel_service_name: str = "aifinops-api"
    metrics_port: int = Field(default=9090, ge=1, le=65535)

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_testing(self) -> bool:
        return self.app_env == "testing"


@lru_cache
def get_settings() -> Settings:
    """Return the cached Settings singleton. Override in tests via dependency_overrides."""
    return Settings()
