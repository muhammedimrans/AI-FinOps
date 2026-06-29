from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Response, status

from app.api.deps import ContainerDep
from app.core.database import check_database
from app.core.redis import check_redis

router = APIRouter(tags=["observability"])

APP_VERSION = "0.1.0"


def _overall_status(checks: list[dict[str, Any]]) -> str:
    statuses = {c["status"] for c in checks}
    if statuses == {"healthy"}:
        return "healthy"
    if "healthy" in statuses:
        return "degraded"
    return "unhealthy"


@router.get(
    "/health",
    summary="Liveness check",
    description=(
        "Returns the health status of the API and its dependencies. "
        "Always returns HTTP 200; callers should inspect the `status` field. "
        "Use /ready for load-balancer traffic gating."
    ),
    response_model=None,
)
async def health(container: ContainerDep) -> dict[str, Any]:
    db_result = await check_database(container.engine)
    redis_result = await check_redis(container.redis)

    checks = [
        {"name": "postgres", **db_result},
        {"name": "redis", **redis_result},
    ]

    return {
        "status": _overall_status(checks),
        "version": APP_VERSION,
        "uptime": time.monotonic(),
        "timestamp": _utc_now(),
        "dependencies": checks,
    }


@router.get(
    "/ready",
    summary="Readiness check",
    description=(
        "Used by load balancers to determine whether this instance should "
        "receive traffic. Returns 200 when ready, 503 when not."
    ),
    response_model=None,
)
async def ready(container: ContainerDep, response: Response) -> dict[str, Any]:
    db_result = await check_database(container.engine)

    checks = [
        {
            "name": "database",
            "passed": db_result["status"] == "healthy",
            "message": db_result.get("error"),
        },
    ]

    all_passed = all(c["passed"] for c in checks)

    if not all_passed:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "ready": all_passed,
        "checks": checks,
    }


@router.get(
    "/metrics",
    summary="Prometheus metrics",
    description=(
        "Returns application metrics in Prometheus text exposition format. "
        "In production, Prometheus scrapes this endpoint directly."
    ),
    response_class=Response,
    responses={
        200: {
            "content": {"text/plain": {}},
            "description": "Prometheus metrics",
        }
    },
)
async def metrics() -> Response:
    payload = (
        "# HELP aifinops_up Whether the application is up and running\n"
        "# TYPE aifinops_up gauge\n"
        f'aifinops_up{{version="{APP_VERSION}"}} 1\n'
        "\n"
        "# HELP aifinops_info Static application info\n"
        "# TYPE aifinops_info gauge\n"
        f'aifinops_info{{version="{APP_VERSION}"}} 1\n'
        "\n"
        "# HELP aifinops_http_requests_total Total HTTP requests received\n"
        "# TYPE aifinops_http_requests_total counter\n"
        "aifinops_http_requests_total 0\n"
        "\n"
        "# HELP aifinops_http_request_duration_seconds HTTP request duration\n"
        "# TYPE aifinops_http_request_duration_seconds histogram\n"
        'aifinops_http_request_duration_seconds_bucket{le="0.1"} 0\n'
        'aifinops_http_request_duration_seconds_bucket{le="0.5"} 0\n'
        'aifinops_http_request_duration_seconds_bucket{le="1.0"} 0\n'
        'aifinops_http_request_duration_seconds_bucket{le="+Inf"} 0\n'
        "aifinops_http_request_duration_seconds_sum 0\n"
        "aifinops_http_request_duration_seconds_count 0\n"
    )
    return Response(
        content=payload,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


def _utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()
