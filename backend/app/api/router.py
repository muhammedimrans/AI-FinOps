from fastapi import APIRouter

from app.api.v1 import (
    alerts,
    analytics,
    auth,
    budgets,
    dashboard,
    health,
    ingest,
    organizations,
    pricing,
    projects,
    provider_connections,
    providers,
    rbac,
    realtime,
    usage,
)

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

# EP-10 — Dashboard API & Executive Analytics Layer
api_router.include_router(dashboard.router, prefix="/v1")

# EP-12.1 — Organization Context
api_router.include_router(organizations.router, prefix="/v1")

# EP-13 — Member Management & RBAC
api_router.include_router(rbac.router, prefix="/v1")

# EP-16 — Usage Ingestion Platform
api_router.include_router(ingest.router, prefix="/v1")

# EP-19.1 — Real-Time Telemetry Platform Foundation
api_router.include_router(realtime.router, prefix="/v1")

# EP-19.3 — Alert Rule Engine & Notification Persistence
api_router.include_router(alerts.router, prefix="/v1")

# EP-22 — Provider Connections (real, persisted)
api_router.include_router(provider_connections.router, prefix="/v1")

# EP-23 — Projects CRUD
api_router.include_router(projects.router, prefix="/v1")

# EP-24.2 — Budgets, Spend Alerts & Cost Monitoring
api_router.include_router(budgets.router, prefix="/v1")
