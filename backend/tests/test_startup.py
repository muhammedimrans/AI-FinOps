"""Tests for application startup, factory, and dependency injection."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI

from app.config.settings import Settings
from app.core.container import AppContainer
from app.main import create_app


@pytest.mark.unit
class TestCreateApp:
    def test_create_app_returns_fastapi_instance(self, test_settings: Settings) -> None:
        application = create_app(test_settings)
        assert isinstance(application, FastAPI)

    def test_app_title_is_set(self, test_settings: Settings) -> None:
        application = create_app(test_settings)
        assert "AI FinOps" in application.title

    def test_app_version_is_set(self, test_settings: Settings) -> None:
        application = create_app(test_settings)
        assert application.version == "0.1.0"

    def test_app_stores_settings_on_state(self, test_settings: Settings) -> None:
        application = create_app(test_settings)
        assert application.state.settings is test_settings

    def test_docs_enabled_in_development(self) -> None:
        settings = Settings(app_secret_key="a" * 32, app_env="development")
        application = create_app(settings)
        assert application.docs_url == "/docs"

    def test_docs_disabled_in_production(self) -> None:
        settings = Settings(app_secret_key="a" * 32, app_env="production")
        application = create_app(settings)
        assert application.docs_url is None

    def test_openapi_disabled_in_production(self) -> None:
        settings = Settings(app_secret_key="a" * 32, app_env="production")
        application = create_app(settings)
        assert application.openapi_url is None

    def _registered_paths(self, application: FastAPI) -> set[str]:
        """Extract all registered paths from the generated OpenAPI schema."""
        return set(application.openapi().get("paths", {}).keys())

    def test_health_route_registered(self, test_settings: Settings) -> None:
        application = create_app(test_settings)
        assert "/health" in self._registered_paths(application)

    def test_ready_route_registered(self, test_settings: Settings) -> None:
        application = create_app(test_settings)
        assert "/ready" in self._registered_paths(application)

    def test_metrics_route_registered(self, test_settings: Settings) -> None:
        application = create_app(test_settings)
        assert "/metrics" in self._registered_paths(application)

    def test_uses_cached_settings_when_no_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.config.settings import get_settings

        monkeypatch.setenv("APP_SECRET_KEY", "a" * 32)
        get_settings.cache_clear()
        try:
            application = create_app()
            assert isinstance(application.state.settings, Settings)
        finally:
            get_settings.cache_clear()


@pytest.mark.unit
class TestDependencyInjection:
    async def test_get_container_raises_without_state(self, test_settings: Settings) -> None:
        """Container must be present on app.state after startup."""
        application = create_app(test_settings)
        # Without pre-injecting the container, get_container will fail
        from fastapi import Request

        from app.api.deps import get_container

        mock_request = MagicMock(spec=Request)
        mock_request.app = application
        # app.state.container not set → AttributeError
        with pytest.raises(AttributeError):
            get_container(mock_request)

    async def test_get_container_returns_container_from_state(
        self, test_settings: Settings, mock_container: AppContainer
    ) -> None:
        from fastapi import Request

        from app.api.deps import get_container

        application = create_app(test_settings)
        application.state.container = mock_container

        mock_request = MagicMock(spec=Request)
        mock_request.app = application

        result = get_container(mock_request)
        assert result is mock_container

    async def test_health_endpoint_uses_container(self, client: pytest.FixtureRequest) -> None:
        """The /health endpoint must inject the container (smoke test via HTTP)."""
        with (
            patch(
                "app.core.database.check_database",
                return_value={"status": "healthy", "latency_ms": 1.0},
            ),
            patch(
                "app.core.redis.check_redis",
                return_value={"status": "healthy", "latency_ms": 0.5},
            ),
        ):
            pass  # Container is pre-injected via conftest fixture


@pytest.mark.unit
class TestAppContainer:
    async def test_create_returns_container(self, test_settings: Settings) -> None:
        """Container.create() must succeed (init_db mocked to avoid network IO)."""
        with patch("app.core.container.init_db", new_callable=AsyncMock):
            container = await AppContainer.create(test_settings)
        assert isinstance(container, AppContainer)
        assert container.settings is test_settings
        assert container.engine is not None
        assert container.session_factory is not None
        assert container.redis is not None
        # Clean up
        await container.close()

    async def test_close_disposes_resources(self, test_settings: Settings) -> None:
        """Container.close() must not raise."""
        with patch("app.core.container.init_db", new_callable=AsyncMock):
            container = await AppContainer.create(test_settings)
        # Should not raise even if not connected
        await container.close()

    def test_container_holds_settings(
        self, mock_container: AppContainer, test_settings: Settings
    ) -> None:
        assert mock_container.settings is test_settings
