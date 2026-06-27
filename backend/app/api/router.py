from fastapi import APIRouter

from app.api.v1 import health

api_router = APIRouter()

# Observability endpoints live at root (no /v1 prefix) — they must be
# reachable by load balancers without any version prefix.
api_router.include_router(health.router)

# Future v1 routers are added here with prefix="/v1"
# Example:
# api_router.include_router(usage.router, prefix="/v1")
# api_router.include_router(organizations.router, prefix="/v1")
