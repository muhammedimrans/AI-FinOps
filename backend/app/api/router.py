from fastapi import APIRouter

from app.api.v1 import analytics, auth, health, pricing, providers, usage

api_router = APIRouter()

# Observability endpoints live at root (no /v1 prefix) — they must be
# reachable by load balancers without any version prefix.
api_router.include_router(health.router)

# v1 endpoints
api_router.include_router(auth.router, prefix="/v1")
api_router.include_router(providers.router, prefix="/v1")
api_router.include_router(usage.router, prefix="/v1")

# EP-09 — Cost & Analytics Engine
api_router.include_router(pricing.router, prefix="/v1")
api_router.include_router(analytics.router, prefix="/v1")
