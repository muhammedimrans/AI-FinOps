"""Tests for GET /health, GET /ready, GET /metrics endpoints."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import AsyncClient

# All patches target the module where check_database/check_redis are *called*
# (app.api.v1.health), not where they are *defined* (app.core.*).
_PATCH_DB = "app.api.v1.health.check_database"
_PATCH_REDIS = "app.api.v1.health.check_redis"

_DB_HEALTHY = {"status": "healthy", "latency_ms": 1.2}
_REDIS_HEALTHY = {"status": "healthy", "latency_ms": 0.5}
_DB_UNHEALTHY = {"status": "unhealthy", "latency_ms": None, "error": "connection refused"}
_REDIS_UNHEALTHY = {"status": "unhealthy", "latency_ms": None, "error": "connection refused"}


@pytest.mark.unit
class TestHealthEndpoint:
    async def test_returns_200(self, client: AsyncClient) -> None:
        with (
            patch(_PATCH_DB, return_value=_DB_HEALTHY),
            patch(_PATCH_REDIS, return_value=_REDIS_HEALTHY),
        ):
            response = await client.get("/health")
        assert response.status_code == 200

    async def test_response_shape(self, client: AsyncClient) -> None:
        with (
            patch(_PATCH_DB, return_value=_DB_HEALTHY),
            patch(_PATCH_REDIS, return_value=_REDIS_HEALTHY),
        ):
            response = await client.get("/health")
        body = response.json()
        assert "status" in body
        assert "version" in body
        assert "timestamp" in body
        assert "dependencies" in body
        assert isinstance(body["dependencies"], list)

    async def test_status_healthy_when_all_up(self, client: AsyncClient) -> None:
        with (
            patch(_PATCH_DB, return_value=_DB_HEALTHY),
            patch(_PATCH_REDIS, return_value=_REDIS_HEALTHY),
        ):
            response = await client.get("/health")
        assert response.json()["status"] == "healthy"

    async def test_status_degraded_when_one_dependency_down(self, client: AsyncClient) -> None:
        with (
            patch(_PATCH_DB, return_value=_DB_UNHEALTHY),
            patch(_PATCH_REDIS, return_value=_REDIS_HEALTHY),
        ):
            response = await client.get("/health")
        assert response.status_code == 200  # health always returns 200
        assert response.json()["status"] == "degraded"

    async def test_status_unhealthy_when_all_dependencies_down(self, client: AsyncClient) -> None:
        with (
            patch(_PATCH_DB, return_value=_DB_UNHEALTHY),
            patch(_PATCH_REDIS, return_value=_REDIS_UNHEALTHY),
        ):
            response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "unhealthy"

    async def test_version_field_present(self, client: AsyncClient) -> None:
        with (
            patch(_PATCH_DB, return_value=_DB_HEALTHY),
            patch(_PATCH_REDIS, return_value=_REDIS_HEALTHY),
        ):
            response = await client.get("/health")
        assert response.json()["version"] == "0.1.0"

    async def test_dependencies_include_postgres_and_redis(self, client: AsyncClient) -> None:
        with (
            patch(_PATCH_DB, return_value=_DB_HEALTHY),
            patch(_PATCH_REDIS, return_value=_REDIS_HEALTHY),
        ):
            response = await client.get("/health")
        names = {d["name"] for d in response.json()["dependencies"]}
        assert "postgres" in names
        assert "redis" in names


@pytest.mark.unit
class TestReadyEndpoint:
    async def test_returns_200_when_ready(self, client: AsyncClient) -> None:
        with patch(_PATCH_DB, return_value=_DB_HEALTHY):
            response = await client.get("/ready")
        assert response.status_code == 200
        assert response.json()["ready"] is True

    async def test_returns_503_when_database_down(self, client: AsyncClient) -> None:
        with patch(_PATCH_DB, return_value=_DB_UNHEALTHY):
            response = await client.get("/ready")
        assert response.status_code == 503
        assert response.json()["ready"] is False

    async def test_response_shape(self, client: AsyncClient) -> None:
        with patch(_PATCH_DB, return_value=_DB_HEALTHY):
            response = await client.get("/ready")
        body = response.json()
        assert "ready" in body
        assert "checks" in body
        assert isinstance(body["checks"], list)

    async def test_checks_include_database(self, client: AsyncClient) -> None:
        with patch(_PATCH_DB, return_value=_DB_HEALTHY):
            response = await client.get("/ready")
        names = {c["name"] for c in response.json()["checks"]}
        assert "database" in names


@pytest.mark.unit
class TestMetricsEndpoint:
    async def test_returns_200(self, client: AsyncClient) -> None:
        response = await client.get("/metrics")
        assert response.status_code == 200

    async def test_content_type_is_prometheus(self, client: AsyncClient) -> None:
        response = await client.get("/metrics")
        assert "text/plain" in response.headers["content-type"]
        assert "0.0.4" in response.headers["content-type"]

    async def test_response_contains_up_metric(self, client: AsyncClient) -> None:
        response = await client.get("/metrics")
        assert "aifinops_up" in response.text

    async def test_response_contains_info_metric(self, client: AsyncClient) -> None:
        response = await client.get("/metrics")
        assert "aifinops_info" in response.text

    async def test_response_contains_requests_metric(self, client: AsyncClient) -> None:
        response = await client.get("/metrics")
        assert "aifinops_http_requests_total" in response.text

    async def test_response_is_valid_prometheus_format(self, client: AsyncClient) -> None:
        response = await client.get("/metrics")
        lines = response.text.strip().split("\n")
        for line in lines:
            if line and not line.startswith("#"):
                parts = line.rsplit(" ", 1)
                assert len(parts) == 2, f"Invalid metric line: {line!r}"
                float(parts[1])
