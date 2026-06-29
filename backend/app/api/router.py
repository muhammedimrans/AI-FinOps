from fastapi import APIRouter

from app.api.v1 import auth, health

api_router = APIRouter()

# Observability endpoints live at root (no /v1 prefix) — they must be
# reachable by load balancers without any version prefix.
api_router.include_router(health.router)

# v1 endpoints
api_router.include_router(auth.router, prefix="/v1")
