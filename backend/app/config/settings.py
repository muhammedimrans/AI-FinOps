from __future__ import annotations

from functools import lru_cache
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from pydantic import AliasChoices, Field, SecretStr, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# libpq connection parameters that asyncpg does not understand.
_ASYNCPG_UNSUPPORTED_PARAMS = frozenset({"channel_binding", "gssencmode", "target_session_attrs"})


def _normalize_asyncpg_url(url: str) -> str:
    """
    Normalize a PostgreSQL connection URL for asyncpg:
      - Rewrites postgres:// and postgresql:// schemes to postgresql+asyncpg
      - Translates sslmode=<val> to ssl=<val>
      - Strips libpq-only parameters asyncpg does not accept
    URLs already using postgresql+asyncpg:// pass through unchanged except
    for the parameter normalization above.
    """
    parsed = urlparse(url)

    # Rewrite scheme
    scheme = parsed.scheme
    if scheme in ("postgres", "postgresql"):
        scheme = "postgresql+asyncpg"

    # Normalize query parameters
    params: list[tuple[str, str]] = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if key in _ASYNCPG_UNSUPPORTED_PARAMS:
            continue
        if key == "sslmode":
            params.append(("ssl", value))
        else:
            params.append((key, value))

    normalized = urlunparse(
        (scheme, parsed.netloc, parsed.path, parsed.params, urlencode(params), parsed.fragment)
    )
    return normalized


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
    # EP-22: the previous-generation APP_SECRET_KEY, set only during a secret
    # rotation window. EncryptionService falls back to this key to decrypt
    # provider credentials encrypted before the rotation, so rotating
    # APP_SECRET_KEY does not require a bulk re-encryption migration. Unset
    # (None) outside of an active rotation.
    app_secret_key_previous: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("APP_SECRET_KEY_PREVIOUS", "app_secret_key_previous"),
    )

    @model_validator(mode="after")
    def _enforce_secret_in_production(self) -> Settings:
        if self.app_env == "production" and self.app_secret_key.get_secret_value() == _DEV_SECRET:
            raise ValueError("APP_SECRET_KEY must be set to a secure random value in production.")
        if self.app_env == "production" and len(self.jwt_secret.get_secret_value()) < 32:
            raise ValueError(
                "JWT_SECRET must be set to a secure random value of at least 32 characters "
                "in production — an empty or short secret makes access tokens forgeable."
            )
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
    # Restricted to HMAC variants — prevents configuration-driven downgrade
    # to "none" or accidental asymmetric-key misconfiguration.
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = Field(
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
    api_cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "https://op.0protocol.net",
        "https://costorah.com",
        "https://www.costorah.com",
        "https://app.costorah.com",
    ]

    # ─── Session cookie (ADR-006 / EP-21.2) ────────────────────────────────────
    # Domain attribute for the browser-session cookie set by login/register.
    # None (the local-dev default) yields a host-only cookie — correct for
    # localhost, since cookies are not port-scoped and a host-only cookie
    # set by the API is sent back to that same API regardless of which
    # origin/port the calling page was served from. In production this is
    # set to ".costorah.com" so the cookie is valid on both costorah.com
    # (website) and app.costorah.com (dashboard) — see CLAUDE.md §6.
    session_cookie_domain: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SESSION_COOKIE_DOMAIN", "session_cookie_domain"),
    )

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
            return _normalize_asyncpg_url(self.database_url_override)
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

    # ─── Background usage-sync scheduler (EP-23.4) ─────────────────────────────
    # The tick loop itself is always constructed (so the status/monitoring
    # endpoints always have something to report), but only started
    # automatically by AppContainer.create() — set False to disable entirely
    # (e.g. a worker-less deployment, or to run sync exclusively via the
    # manual EP-23.3 endpoints).
    scheduler_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("SCHEDULER_ENABLED", "scheduler_enabled"),
    )
    # How often the loop wakes up to check which organizations are due —
    # independent of any organization's own configured sync interval
    # (5m/15m/1h/6h/24h, see app.services.usage_sync_scheduler).
    scheduler_tick_interval_seconds: int = Field(
        default=60,
        ge=10,
        le=3600,
        validation_alias=AliasChoices(
            "SCHEDULER_TICK_INTERVAL_SECONDS", "scheduler_tick_interval_seconds"
        ),
    )

    # ─── Transactional email (EP-24.4) ─────────────────────────────────────────
    # Production provider is Resend; both variables are already provisioned in
    # Render's environment per EP-24.4's own brief. Optional here (not
    # required=...) so every environment without them (local dev, CI, the
    # test suite) keeps working — ResendEmailProvider treats a missing key as
    # "sending is disabled" and logs+skips rather than raising, matching this
    # codebase's established graceful-missing-config pattern (e.g. the
    # optional per-provider API keys above).
    resend_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("RESEND_API_KEY", "resend_api_key"),
    )
    email_from: str | None = Field(
        default=None,
        validation_alias=AliasChoices("EMAIL_FROM", "email_from"),
    )
    # The user-facing app the verification/reset links point at — the
    # dashboard's own public routes (/verify-email, /reset-password, EP-05)
    # already implement the token-consuming pages these links land on. Falls
    # back to the dashboard's own local-dev default (Vite on :5173) so local
    # development needs no extra configuration.
    dashboard_url: str = Field(
        default="http://localhost:5173",
        validation_alias=AliasChoices("DASHBOARD_URL", "VITE_DASHBOARD_URL", "dashboard_url"),
    )

    # ─── Email delivery-event webhooks (EP-25.3) ───────────────────────────────
    # Resend signs every webhook request using Svix (HMAC-SHA256, base64-encoded
    # secret prefixed "whsec_") — this is the shared secret used to verify that
    # signature (app/email/webhook.py). Optional, mirroring resend_api_key: an
    # environment without it configured simply can't receive delivery events
    # (POST /v1/webhooks/resend returns 503), it never blocks anything email
    # ever needed to work before this EP.
    resend_webhook_secret: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("RESEND_WEBHOOK_SECRET", "resend_webhook_secret"),
    )

    @model_validator(mode="after")
    def _enforce_email_config_in_production(self) -> Settings:
        if self.app_env == "production" and (not self.resend_api_key or not self.email_from):
            raise ValueError(
                "RESEND_API_KEY and EMAIL_FROM must both be set in production — "
                "verification and password-reset emails cannot be delivered without them."
            )
        return self

    # ─── Google OAuth (EP-24.5) ─────────────────────────────────────────────────
    # Optional here for the same reason resend_api_key/email_from are optional
    # above — local dev/CI/most of the test suite have no Google app
    # registered. The /v1/auth/google/* endpoints return a clear 503 rather
    # than crashing when unconfigured (see app/auth/google_oauth.py).
    google_client_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GOOGLE_CLIENT_ID", "google_client_id"),
    )
    google_client_secret: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("GOOGLE_CLIENT_SECRET", "google_client_secret"),
    )
    # This backend's own public URL — needed to build the OAuth redirect_uri
    # Google calls back to (`{api_base_url}/v1/auth/google/callback`), which
    # must exactly match one of the URIs registered in Google Cloud Console.
    # Distinct from dashboard_url (the frontend), which the callback itself
    # redirects *to* once the session is established.
    api_base_url: str = Field(
        default="http://localhost:8000",
        validation_alias=AliasChoices("API_BASE_URL", "api_base_url"),
    )

    @property
    def google_oauth_configured(self) -> bool:
        """True once both Google credentials are present.

        Deliberately NOT enforced at startup the way resend_api_key/email_from
        are (§ EP-24.4's `_enforce_email_config_in_production`) — Google
        sign-in is an additive, optional login method (Part 1's "Continue
        with Google" augments, never replaces, password login), so a
        production deploy without a Google Cloud Console app registered yet
        must still start cleanly. The /v1/auth/google/* endpoints check this
        property themselves and return 503 rather than crashing.
        """
        return bool(self.google_client_id) and bool(self.google_client_secret)

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
