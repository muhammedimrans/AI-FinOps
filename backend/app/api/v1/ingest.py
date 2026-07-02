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
from typing import Annotated

import structlog
from fastapi import APIRouter, HTTPException, status

from app.api.deps import DbDep
from app.auth.api_key_auth import RequireApiKeyPermission
from app.auth.rbac import Permission
from app.schemas.usage_ingestion import IngestUsageRequest, IngestUsageResponse
from app.services.api_key_auth_service import ApiKeyAuthContext
from app.services.usage_ingestion_service import UnknownProjectError, UsageIngestionService

log = structlog.get_logger(__name__)

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

    return IngestUsageResponse(
        usage_id=record.id,
        request_id=record.request_id,
        # Always the time the record was *actually* stored — for a
        # duplicate that's the original call, not this replay.
        processed_at=record.ingested_at,
        duplicate=is_duplicate,
    )
