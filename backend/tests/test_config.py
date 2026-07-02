"""Tests for configuration loading and Settings validation."""

from __future__ import annotations

import pytest

from app.config.settings import Settings, _normalize_asyncpg_url, get_settings


@pytest.mark.unit
class TestSettings:
    def test_settings_load_with_defaults(self) -> None:
        settings = Settings()
        assert settings is not None

    def test_settings_load_with_explicit_secret(self) -> None:
        settings = Settings(app_secret_key="a" * 32)
        assert settings is not None

    def test_default_env_is_development(self) -> None:
        settings = Settings(app_secret_key="a" * 32)
        assert settings.app_env == "development"

    def test_default_log_level_is_info(self) -> None:
        settings = Settings(app_secret_key="a" * 32)
        assert settings.app_log_level == "INFO"

    def test_database_url_computed_from_parts(self) -> None:
        settings = Settings(
            app_secret_key="a" * 32,
            postgres_host="db-host",
            postgres_port=5432,
            postgres_db="mydb",
            postgres_user="myuser",
            postgres_password="mypass",
        )
        assert settings.database_url == "postgresql+asyncpg://myuser:mypass@db-host:5432/mydb"

    def test_database_url_sync_uses_psycopg2(self) -> None:
        settings = Settings(app_secret_key="a" * 32)
        assert "psycopg2" in settings.database_url_sync

    def test_redis_url_computed_from_parts(self) -> None:
        settings = Settings(
            app_secret_key="a" * 32,
            redis_host="cache",
            redis_port=6380,
            redis_db=1,
        )
        assert settings.redis_url == "redis://cache:6380/1"

    def test_redis_url_includes_password_when_set(self) -> None:
        settings = Settings(
            app_secret_key="a" * 32,
            redis_password="secret",
        )
        assert ":secret@" in settings.redis_url

    def test_redis_url_omits_password_when_empty(self) -> None:
        settings = Settings(
            app_secret_key="a" * 32,
            redis_password="",
        )
        assert "@" not in settings.redis_url

    def test_clickhouse_url_is_http(self) -> None:
        settings = Settings(app_secret_key="a" * 32)
        assert settings.clickhouse_url.startswith("http://")

    def test_is_development_true_in_dev(self) -> None:
        settings = Settings(app_secret_key="a" * 32, app_env="development")
        assert settings.is_development is True
        assert settings.is_production is False

    def test_is_production_true_in_prod(self) -> None:
        settings = Settings(app_secret_key="a" * 32, jwt_secret="j" * 32, app_env="production")
        assert settings.is_production is True
        assert settings.is_development is False

    def test_is_testing_true_in_test(self) -> None:
        settings = Settings(app_secret_key="a" * 32, app_env="testing")
        assert settings.is_testing is True

    def test_secret_key_minimum_length_enforced(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            Settings(app_secret_key="short")

    def test_default_secret_rejected_in_production(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="APP_SECRET_KEY"):
            Settings(app_env="production")

    def test_empty_jwt_secret_rejected_in_production(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="JWT_SECRET"):
            Settings(app_secret_key="a" * 32, app_env="production")

    def test_short_jwt_secret_rejected_in_production(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="JWT_SECRET"):
            Settings(app_secret_key="a" * 32, jwt_secret="short", app_env="production")

    def test_jwt_secret_not_required_in_development(self) -> None:
        settings = Settings(app_secret_key="a" * 32, app_env="development")
        assert settings.is_development is True

    def test_api_port_range_enforced(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            Settings(app_secret_key="a" * 32, api_port=0)

        with pytest.raises(ValidationError):
            Settings(app_secret_key="a" * 32, api_port=99999)

    def test_cors_origins_defaults_to_local_dev(self) -> None:
        settings = Settings(app_secret_key="a" * 32)
        assert any("localhost" in origin for origin in settings.api_cors_origins)

    def test_test_settings_fixture(self, test_settings: Settings) -> None:
        assert test_settings.app_env == "testing"
        assert test_settings.is_testing is True


@pytest.mark.unit
class TestNormalizeAsyncpgUrl:
    """Unit tests for the _normalize_asyncpg_url helper (no Settings involved)."""

    # ── scheme rewriting ──────────────────────────────────────────────────────

    def test_postgres_scheme_rewritten(self) -> None:
        assert _normalize_asyncpg_url("postgres://u:p@host/db").startswith(
            "postgresql+asyncpg://"
        )

    def test_postgresql_scheme_rewritten(self) -> None:
        assert _normalize_asyncpg_url("postgresql://u:p@host/db").startswith(
            "postgresql+asyncpg://"
        )

    def test_asyncpg_scheme_preserved(self) -> None:
        url = "postgresql+asyncpg://u:p@host/db"
        assert _normalize_asyncpg_url(url) == url

    # ── sslmode translation ───────────────────────────────────────────────────

    def test_sslmode_require_translated(self) -> None:
        out = _normalize_asyncpg_url("postgres://u:p@host/db?sslmode=require")
        assert "ssl=require" in out
        assert "sslmode" not in out

    def test_sslmode_translated_for_postgresql_scheme(self) -> None:
        out = _normalize_asyncpg_url("postgresql://u:p@host/db?sslmode=require")
        assert "ssl=require" in out
        assert "sslmode" not in out

    def test_sslmode_translated_for_asyncpg_scheme(self) -> None:
        out = _normalize_asyncpg_url("postgresql+asyncpg://u:p@host/db?sslmode=require")
        assert "ssl=require" in out
        assert "sslmode" not in out

    def test_ssl_already_present_not_duplicated(self) -> None:
        out = _normalize_asyncpg_url("postgresql+asyncpg://u:p@host/db?ssl=require")
        assert out.count("ssl=require") == 1

    # ── unsupported libpq parameter removal ──────────────────────────────────

    def test_channel_binding_removed(self) -> None:
        out = _normalize_asyncpg_url(
            "postgres://u:p@host/db?sslmode=require&channel_binding=require"
        )
        assert "channel_binding" not in out
        assert "ssl=require" in out

    def test_gssencmode_removed(self) -> None:
        out = _normalize_asyncpg_url("postgres://u:p@host/db?gssencmode=disable")
        assert "gssencmode" not in out

    def test_target_session_attrs_removed(self) -> None:
        out = _normalize_asyncpg_url(
            "postgres://u:p@host/db?target_session_attrs=read-write"
        )
        assert "target_session_attrs" not in out

    def test_all_unsupported_params_removed_together(self) -> None:
        raw = (
            "postgres://u:p@host/db"
            "?sslmode=require"
            "&channel_binding=require"
            "&gssencmode=disable"
            "&target_session_attrs=read-write"
        )
        out = _normalize_asyncpg_url(raw)
        assert "channel_binding" not in out
        assert "gssencmode" not in out
        assert "target_session_attrs" not in out
        assert "ssl=require" in out
        assert out.startswith("postgresql+asyncpg://")

    # ── supported parameters preserved ───────────────────────────────────────

    def test_connect_timeout_preserved(self) -> None:
        out = _normalize_asyncpg_url(
            "postgres://u:p@host/db?sslmode=require&connect_timeout=10"
        )
        assert "connect_timeout=10" in out

    def test_no_query_params_unchanged(self) -> None:
        out = _normalize_asyncpg_url("postgresql+asyncpg://u:p@host/db")
        assert "?" not in out

    # ── Neon/Render real-world URL shape ─────────────────────────────────────

    def test_neon_url_fully_normalized(self) -> None:
        neon = (
            "postgresql://user:pass@ep-xyz.us-east-1.aws.neon.tech/neondb"
            "?sslmode=require&channel_binding=require"
        )
        out = _normalize_asyncpg_url(neon)
        assert out.startswith("postgresql+asyncpg://")
        assert "ssl=require" in out
        assert "sslmode" not in out
        assert "channel_binding" not in out


@pytest.mark.unit
class TestDatabaseUrlNormalizationViaSettings:
    """Smoke-tests that Settings.database_url delegates to the normalizer."""

    BASE = "a" * 32

    def _url(self, raw: str) -> str:
        return Settings(app_secret_key=self.BASE, DATABASE_URL=raw).database_url

    def test_postgres_scheme_via_settings(self) -> None:
        assert self._url("postgres://u:p@host/db").startswith("postgresql+asyncpg://")

    def test_sslmode_via_settings(self) -> None:
        url = self._url("postgres://u:p@host/db?sslmode=require")
        assert "ssl=require" in url
        assert "sslmode" not in url

    def test_channel_binding_stripped_via_settings(self) -> None:
        url = self._url(
            "postgres://u:p@host/db?sslmode=require&channel_binding=require"
        )
        assert "channel_binding" not in url


@pytest.mark.unit
class TestGetSettings:
    def test_get_settings_returns_settings_instance(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_SECRET_KEY", "a" * 32)
        # Clear cache before test
        get_settings.cache_clear()
        try:
            settings = get_settings()
            assert isinstance(settings, Settings)
        finally:
            get_settings.cache_clear()

    def test_get_settings_is_cached(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_SECRET_KEY", "a" * 32)
        get_settings.cache_clear()
        try:
            s1 = get_settings()
            s2 = get_settings()
            assert s1 is s2
        finally:
            get_settings.cache_clear()
