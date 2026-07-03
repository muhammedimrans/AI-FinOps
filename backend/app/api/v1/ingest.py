"""Usage Ingestion API — EP-16.

Endpoint:
  POST /v1/ingest/usage — accept one usage record from an authenticated
  integration (Monitoring Agent, SDK, gateway, proxy, custom script).

Authentication
--------------
Organization API Key only (`Authorization: Bearer costorah_live_...`),
requiring the `usage:write` scope — this is a machine-to-machine endpoint,
not a dashboard action, so unlike the dual-auth GET .../api-keys from
EP-15, there is no JWT fallback here.

Idempotency
-----------
A duplicate `request_id` (scoped to the authenticated organization) is not
an error: the original record is returned with `duplicate: true` and HTTP
200, matching this ticket's own literal response examples and the
idempotency-key convention used by every reference architecture it cites
(Stripe's Idempotency-Key header behaves identically — a replayed request
returns the original response, not an error).
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.dedup import budget_scope
from app.alerts.dispatcher import AlertService
from app.alerts.rule_engine import RuleEngine
from app.api.deps import DbDep, EventBusDep
from app.auth.api_key_auth import RequireApiKeyPermission
from app.auth.rbac import Permission
from app.models.alert import AlertSeverity, AlertType
from app.realtime.event_bus import EventBus
from app.realtime.events import EventType, RealtimeEvent
from app.repositories.project_repository import ProjectRepository
from app.repositories.usage_record_repository import UsageRecordRepository
from app.schemas.usage_ingestion import IngestUsageRequest, IngestUsageResponse
from app.services.api_key_auth_service import ApiKeyAuthContext
from app.services.usage_ingestion_service import UnknownProjectError, UsageIngestionService

log = structlog.get_logger(__name__)

# (alert_type, severity) checked on every ingestion with a budgeted
# project — exceeded first so a single ingestion that crosses both
# thresholds in one shot reports the more severe one as well.
_BUDGET_CHECKS: tuple[tuple[AlertType, AlertSeverity], ...] = (
    (AlertType.BUDGET_EXCEEDED, AlertSeverity.CRITICAL),
    (AlertType.BUDGET_THRESHOLD, AlertSeverity.HIGH),
)

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post(
    "/usage",
    response_model=IngestUsageResponse,
    status_code=status.HTTP_200_OK,
    summary="Ingest one usage record",
    description=(
        "Accepts a single AI usage record from an authenticated integration "
        "and stores it, updates cost aggregates, and makes it immediately "
        "visible through the existing dashboard/analytics endpoints. "
        "Requires an Organization API Key with the `usage:write` scope."
    ),
    openapi_extra={"security": [{"ApiKeyAuth": []}]},
    responses={
        200: {
            "description": "Ingested (or a duplicate request_id resolved to the original record)",
            "content": {
                "application/json": {
                    "examples": {
                        "created": {
                            "summary": "New record",
                            "value": {
                                "success": True,
                                "usage_id": "5b1e2b2e-6b1a-4b8e-9b1a-5b1e2b2e6b1a",
                                "request_id": "req_123456",
                                "processed_at": "2026-07-02T18:15:22Z",
                                "duplicate": False,
                            },
                        },
                        "duplicate": {
                            "summary": "Duplicate request_id",
                            "value": {
                                "success": True,
                                "usage_id": "5b1e2b2e-6b1a-4b8e-9b1a-5b1e2b2e6b1a",
                                "request_id": "req_123456",
                                "processed_at": "2026-07-02T18:15:22Z",
                                "duplicate": True,
                            },
                        },
                    }
                }
            },
        },
        400: {"description": "Payload failed a business-rule check (e.g. malformed metadata)"},
        401: {"description": "Invalid or expired API Key"},
        403: {"description": "Organization suspended, or the key lacks usage:write"},
        404: {"description": "project_id does not exist in this organization"},
        422: {"description": "Payload failed schema validation (types, ranges, required fields)"},
    },
)
async def ingest_usage(
    body: IngestUsageRequest,
    db: DbDep,
    event_bus: EventBusDep,
    current_api_key: Annotated[
        ApiKeyAuthContext, RequireApiKeyPermission(Permission.USAGE_WRITE)
    ],
) -> IngestUsageResponse:
    start = time.monotonic()
    service = UsageIngestionService(db)

    try:
        record, is_duplicate = await service.ingest(
            organization=current_api_key.organization,
            api_key_id=current_api_key.api_key_id,
            payload=body,
        )
    except UnknownProjectError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="project_id does not exist in this organization",
        ) from exc

    elapsed_ms = round((time.monotonic() - start) * 1000, 2)
    log.info(
        "usage_ingested",
        organization_id=str(current_api_key.organization_id),
        provider=record.provider,
        model=record.model,
        request_id=record.request_id,
        duplicate=is_duplicate,
        duration_ms=elapsed_ms,
    )

    if not is_duplicate:
        await event_bus.publish(
            RealtimeEvent(
                organization_id=current_api_key.organization_id,
                type=EventType.USAGE_CREATED,
                payload={
                    "usage_id": str(record.id),
                    "provider": record.provider,
                    "model": record.model,
                    "cost": str(record.cost),
                    "currency": record.currency,
                    "total_tokens": record.total_tokens,
                    "status": record.status.value,
                    "project_id": str(record.project_id) if record.project_id else None,
                },
                trace_id=record.request_id,
            )
        )
        if record.project_id is not None:
            await _check_budget_alerts(
                db,
                event_bus,
                organization_id=current_api_key.organization_id,
                project_id=record.project_id,
            )

    return IngestUsageResponse(
        usage_id=record.id,
        request_id=record.request_id,
        # Always the time the record was *actually* stored — for a
        # duplicate that's the original call, not this replay.
        processed_at=record.ingested_at,
        duplicate=is_duplicate,
    )


async def _check_budget_alerts(
    db: AsyncSession,
    event_bus: EventBus,
    *,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
) -> None:
    """EP-19.3 — evaluates the project's `budget_threshold`/`budget_exceeded`
    AlertRule rows (if the organization has configured any) against
    month-to-date spend. A project with no `budget` set, or an
    organization with no rules configured for these two types, simply has
    nothing to evaluate — this never fabricates a default threshold.
    Errors here are logged and swallowed, never raised: a budget-alert
    bug must never fail the usage-ingestion request that triggered it.
    """
    try:
        project = await ProjectRepository(db).get(project_id)
        if project is None or project.budget is None or project.budget <= 0:
            return

        month_to_date = await UsageRecordRepository(db).get_project_month_to_date_total(
            organization_id, project_id, as_of=datetime.now(UTC).date()
        )
        pct_used = float((month_to_date / project.budget) * 100)

        rule_engine = RuleEngine(db)
        alert_service = AlertService(db, event_bus)

        for alert_type, severity in _BUDGET_CHECKS:
            matched_rules = await rule_engine.evaluate_type(
                organization_id=organization_id,
                alert_type=alert_type,
                current_value=pct_used,
            )
            for rule in matched_rules:
                await alert_service.fire(
                    organization_id=organization_id,
                    alert_type=alert_type,
                    severity=severity,
                    title=f"{project.name}: {alert_type.value.replace('_', ' ')}",
                    message=(
                        f"{project.name} has used {pct_used:.1f}% of its "
                        f"{project.budget} budget this month."
                    ),
                    source="ingestion",
                    scope=budget_scope(project_id),
                    rule_id=rule.id,
                    metadata={
                        "project_id": str(project_id),
                        "project_name": project.name,
                        "pct_used": round(pct_used, 2),
                        "budget": str(project.budget),
                        "month_to_date": str(month_to_date),
                    },
                )
    except Exception:
        log.warning(
            "budget_alert_check_failed", organization_id=str(organization_id), exc_info=True
        )
