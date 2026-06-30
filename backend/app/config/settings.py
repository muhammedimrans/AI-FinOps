from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Sentinel used when APP_SECRET_KEY is not set; rejected in production.
_DEV_SECRET = "CHANGE-ME-IN-PRODUCTION-THIS-IS-NOT-SECURE!!"  # noqa: S105


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables / .env file.
    Secrets are typed as SecretStr so they are never printed to logs.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── Application ──────────────────────────────────────────────────────────
    app_name: str = Field(
        default="AI FinOps", validation_alias=AliasChoices("APP_NAME", "app_name")
    )
    app_env: Literal["development", "staging", "production", "testing"] = "development"
    app_debug: bool = False
    app_secret_key: SecretStr = Field(default=_DEV_SECRET, min_length=32)  # type: ignore[assignment]

    @model_validator(mode="after")
    def _enforce_secret_in_production(self) -> Settings:
        if self.app_env == "production" and self.app_secret_key.get_secret_value() == _DEV_SECRET:
            raise ValueError("APP_SECRET_KEY must be set to a secure random value in production.")
        return self

    # Accepts both LOG_LEVEL and APP_LOG_LEVEL for flexibility.
    app_log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        validation_alias=AliasChoices("LOG_LEVEL", "APP_LOG_LEVEL", "app_log_level"),
    )

    # JWT — typed SecretStr so the value is never included in repr/logs.
    jwt_secret: SecretStr = Field(  # type: ignore[assignment]
        default="",
        validation_alias=AliasChoices("JWT_SECRET", "jwt_secret"),
    )
    jwt_algorithm: str = Field(
        default="HS256",
        validation_alias=AliasChoices("JWT_ALGORITHM", "jwt_algorithm"),
    )
    jwt_access_token_expire_minutes: int = Field(
        default=30,
        ge=1,
        le=1440,
        validation_alias=AliasChoices(
            "JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "jwt_access_token_expire_minutes"
        ),
    )
    jwt_refresh_token_expire_days: int = Field(
        default=30,
        ge=1,
        le=365,
        validation_alias=AliasChoices(
            "JWT_REFRESH_TOKEN_EXPIRE_DAYS", "jwt_refresh_token_expire_days"
        ),
    )

    # ─── API server ───────────────────────────────────────────────────────────
    api_host: str = "0.0.0.0"  # noqa: S104
    api_port: int = Field(default=8000, ge=1, le=65535)
    api_workers: int = Field(default=1, ge=1)
    api_reload: bool = False
    api_cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # ─── PostgreSQL ───────────────────────────────────────────────────────────
    # DATABASE_URL takes priority when set (e.g. Neon, Railway, Render).
    # Falls back to individual POSTGRES_* parts for local Docker Compose.
    database_url_override: str | None = Field(
        default=None,
        validation_alias="DATABASE_URL",
    )
    postgres_host: str = "localhost"
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    postgres_db: str = "aifinops"
    postgres_user: str = "aifinops"
    postgres_password: SecretStr = Field(default="aifinops_dev_password")  # type: ignore[assignment]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        if self.database_url_override:
            url = self.database_url_override
            # Render/Heroku supply postgres:// or postgresql:// without a driver
            # specifier. SQLAlchemy defaults to psycopg2 (sync) for these schemes,
            # which is not installed. Rewrite to the asyncpg async dialect.
            if url.startswith("postgres://"):
                url = "postgresql+asyncpg://" + url[len("postgres://"):]
            elif url.startswith("postgresql://") and not url.startswith("postgresql+"):
                url = "postgresql+asyncpg://" + url[len("postgresql://"):]
            # asyncpg does not accept sslmode=; translate to ssl=
            url = url.replace("sslmode=", "ssl=")
            return url
        pw = self.postgres_password.get_secret_value()
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{pw}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url_sync(self) -> str:
        """Synchronous URL used by Alembic migrations."""
        return self.database_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)

    # ─── ClickHouse ───────────────────────────────────────────────────────────
    clickhouse_host: str = "localhost"
    clickhouse_port: int = Field(default=8123, ge=1, le=65535)
    clickhouse_db: str = "aifinops"
    clickhouse_user: str = "aifinops"
    clickhouse_password: SecretStr = Field(default="aifinops_dev_password")  # type: ignore[assignment]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def clickhouse_url(self) -> str:
        return f"http://{self.clickhouse_host}:{self.clickhouse_port}"

    # ─── Redis ────────────────────────────────────────────────────────────────
    redis_host: str = "localhost"
    redis_port: int = Field(default=6379, ge=1, le=65535)
    redis_db: int = Field(default=0, ge=0, le=15)
    redis_password: SecretStr = Field(default="")  # type: ignore[assignment]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def redis_url(self) -> str:
        pw = self.redis_password.get_secret_value()
        if pw:
            return f"redis://:{pw}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    # ─── Provider API keys (EP-07) ────────────────────────────────────────────
    # Optional — used only when a provider config references the env-store key.
    # SecretStr prevents values from appearing in logs or repr output.
    openai_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_API_KEY", "openai_api_key"),
    )
    anthropic_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("ANTHROPIC_API_KEY", "anthropic_api_key"),
    )

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
