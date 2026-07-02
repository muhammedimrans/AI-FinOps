from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.config.settings import Settings, get_settings
from app.core.container import AppContainer
from app.core.logging import configure_from_settings
from app.middleware.request_logging import RequestLoggingMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware

APP_TITLE = "AI FinOps API"
APP_DESCRIPTION = (
    "AI cost observability and financial operations platform. "
    "Track, attribute, forecast, and optimise AI spend across all providers."
)
APP_VERSION = "0.1.0"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """
    Manage the application lifecycle:
    - Startup: configure logging, initialise database/redis, store container.
    - Shutdown: close all connections gracefully.
    """
    settings: Settings = app.state.settings
    configure_from_settings(settings)

    logger = structlog.get_logger(__name__)
    logger.info(
        "starting_api",
        env=settings.app_env,
        version=APP_VERSION,
        debug=settings.app_debug,
    )

    container = await AppContainer.create(settings)
    app.state.container = container

    logger.info("api_started")

    try:
        yield
    finally:
        logger.info("shutting_down_api")
        await container.close()
        logger.info("api_stopped")


def create_app(settings: Settings | None = None) -> FastAPI:
    """
    Application factory.
    Accepts an optional Settings override for testing.
    """
    if settings is None:
        settings = get_settings()

    app = FastAPI(
        title=APP_TITLE,
        description=APP_DESCRIPTION,
        version=APP_VERSION,
        docs_url="/docs" if settings.is_development else None,
        redoc_url="/redoc" if settings.is_development else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # Store settings on app.state so lifespan can read them
    app.state.settings = settings

    # ─── Middleware (outermost first) ────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.is_production)

    # ─── Routers ─────────────────────────────────────────────────────────────
    app.include_router(api_router)

    # ─── OpenAPI security schemes ────────────────────────────────────────────
    # OAuth2PasswordBearer (JWT session auth) is registered automatically by
    # FastAPI from the CurrentUser dependency chain. ApiKeyAuth (EP-15
    # Organization API Keys) has no fastapi.security.* dependency backing it
    # — Authorization is read via a plain Header() so the 401/403 response
    # bodies stay under this app's control — so its scheme must be added
    # explicitly for it to appear in /docs and /openapi.json.
    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=APP_TITLE,
            description=APP_DESCRIPTION,
            version=APP_VERSION,
            routes=app.routes,
        )
        schema.setdefault("components", {}).setdefault("securitySchemes", {})["ApiKeyAuth"] = {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "costorah_live_<random>",
            "description": (
                "Organization API Key (EP-15). Send as "
                "`Authorization: Bearer costorah_live_<key>`. Issued via "
                "POST /v1/organizations/{org_id}/api-keys — the raw key is "
                "shown exactly once at creation and cannot be retrieved again."
            ),
        }
        app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = custom_openapi  # type: ignore[method-assign]

    # ─── Exception handlers ──────────────────────────────────────────────────
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: object, exc: Exception) -> JSONResponse:
        logger = structlog.get_logger(__name__)
        logger.exception("unhandled_exception", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "category": "SERVER",
                    "message": "An unexpected error occurred.",
                },
            },
        )

    return app


# Module-level app instance used by uvicorn
app = create_app()
