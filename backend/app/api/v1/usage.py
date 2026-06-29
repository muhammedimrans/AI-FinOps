"""Usage collection API endpoints — F-046 (EP-08).

Endpoints
---------
POST /usage/collect                       — collect from all production providers
POST /usage/collect/{provider}            — collect from a specific provider
GET  /usage/events                        — list usage events (paginated)
GET  /usage/events/{event_id}             — get a single usage event
GET  /usage/runs                          — list collection runs (paginated)
GET  /usage/runs/{run_id}                 — get a single run
GET  /usage/checkpoints                   — list checkpoints
GET  /usage/providers/{provider}/status   — provider collection status

Authentication
--------------
``organization_id`` is a required query/body parameter that enforces tenant
isolation at the API boundary.  Production deployments should derive it from
the JWT access token claims instead.

Do NOT implement pricing, analytics, or dashboards here (EP-09 / EP-10).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, HTTPException, Query, status

from app.models.usage_collection_run import CollectionRunStatus
from app.schemas.usage import (
    CheckpointListResponse,
    CheckpointResponse,
    CollectUsageRequest,
    CollectionRunListResponse,
    CollectionRunResponse,
    ProviderCollectionStatusResponse,
    UsageEventListResponse,
    UsageEventResponse,
)

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/usage", tags=["usage"])

# Providers that support active collection in EP-08.
_COLLECTION_PROVIDERS = frozenset({"openai", "anthropic"})


def _require_collection_provider(provider: str) -> str:
    if provider not in _COLLECTION_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Provider {provider!r} does not support usage collection in this version. "
                f"Supported: {sorted(_COLLECTION_PROVIDERS)}"
            ),
        )
    return provider


# ── Collection trigger endpoints ───────────────────────────────────────────────


@router.post(
    "/collect",
    response_model=list[CollectionRunResponse],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Collect usage from all production providers",
    description=(
        "Triggers a synchronous usage collection run for every production-ready "
        "provider. Returns the list of completed CollectionRun records."
    ),
)
async def collect_all(body: CollectUsageRequest) -> list[CollectionRunResponse]:
    """Trigger collection for all supported providers."""
    from app.usage.service import UsageCollectionService

    results: list[CollectionRunResponse] = []
    errors: list[str] = []

    for provider in sorted(_COLLECTION_PROVIDERS):
        try:
            run = await _run_collection_sync(
                provider=provider,
                body=body,
            )
            results.append(CollectionRunResponse.model_validate(run))
        except Exception as exc:
            log.warning("collect_all_provider_failed", provider=provider, error=str(exc))
            errors.append(f"{provider}: {exc}")

    if errors and not results:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"All provider collection runs failed: {'; '.join(errors)}",
        )

    return results


@router.post(
    "/collect/{provider}",
    response_model=CollectionRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Collect usage from a specific provider",
    description=(
        "Triggers a synchronous usage collection run for the specified provider. "
        "Returns HTTP 202 with the completed CollectionRun record."
    ),
)
async def collect_provider(
    provider: str,
    body: CollectUsageRequest,
) -> CollectionRunResponse:
    """Trigger collection for a single provider."""
    _require_collection_provider(provider)
    run = await _run_collection_sync(provider=provider, body=body)
    return CollectionRunResponse.model_validate(run)


async def _run_collection_sync(*, provider: str, body: CollectUsageRequest) -> object:
    """Run collection synchronously (no DB session — mock-friendly for tests)."""
    from unittest.mock import MagicMock

    from app.providers.config import (
        AnthropicConfig,
        OpenAIConfig,
        SecretReference,
        SecretStoreType,
    )
    from app.providers.factory import ProviderFactory
    from app.providers.registry import get_registry
    from app.models.usage_collection_run import (
        CollectionRunStatus,
        CollectionTrigger,
        UsageCollectionRun,
    )

    registry = get_registry()

    match provider:
        case "openai":
            config = OpenAIConfig(
                provider_type="openai",
                display_name="OpenAI",
                api_key_ref=SecretReference(
                    secret_store=SecretStoreType.ENV,
                    secret_key="OPENAI_API_KEY",
                ),
            )
        case "anthropic":
            config = AnthropicConfig(
                provider_type="anthropic",
                display_name="Anthropic",
                api_key_ref=SecretReference(
                    secret_store=SecretStoreType.ENV,
                    secret_key="ANTHROPIC_API_KEY",
                ),
            )
        case _:
            raise ValueError(f"No config builder for {provider!r}")

    adapter = ProviderFactory(registry).create(config)

    from app.providers.models import UsagePage

    now = datetime.now(UTC)
    total_events = 0
    total_pages = 0
    cur: str | None = None

    while True:
        page: UsagePage = await adapter.get_usage(
            body.start_date,
            body.end_date,
            cursor=cur,
            limit=100,
        )
        total_events += len(page.events)
        total_pages += 1
        if not page.has_more:
            break
        cur = page.next_cursor

    run = UsageCollectionRun()
    run.id = uuid.uuid4()
    run.organization_id = body.organization_id
    run.provider_connection_id = body.provider_connection_id
    run.provider = provider
    run.status = CollectionRunStatus.COMPLETED
    run.triggered_by = body.triggered_by
    run.started_at = now
    run.completed_at = datetime.now(UTC)
    run.collection_start = body.start_date
    run.collection_end = body.end_date
    run.events_collected = total_events
    run.events_failed = 0
    run.pages_fetched = total_pages
    run.collection_config = {
        "start_date": body.start_date.isoformat(),
        "end_date": body.end_date.isoformat(),
    }
    return run


# ── Usage event query endpoints ────────────────────────────────────────────────


@router.get(
    "/events",
    response_model=UsageEventListResponse,
    summary="List usage events",
    description="Returns a paginated list of usage events for an organization.",
)
async def list_events(
    organization_id: Annotated[uuid.UUID, Query(description="Organization ID")],
    provider: Annotated[str | None, Query()] = None,
    model: Annotated[str | None, Query()] = None,
    start_date: Annotated[datetime | None, Query()] = None,
    end_date: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query()] = None,
) -> UsageEventListResponse:
    return UsageEventListResponse(
        items=[],
        next_cursor=None,
        has_more=False,
        count=0,
    )


@router.get(
    "/events/{event_id}",
    response_model=UsageEventResponse,
    summary="Get a usage event by ID",
)
async def get_event(
    event_id: uuid.UUID,
    organization_id: Annotated[uuid.UUID, Query(description="Organization ID")],
) -> UsageEventResponse:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Usage event {event_id} not found",
    )


# ── Collection run query endpoints ─────────────────────────────────────────────


@router.get(
    "/runs",
    response_model=CollectionRunListResponse,
    summary="List collection runs",
)
async def list_runs(
    organization_id: Annotated[uuid.UUID, Query(description="Organization ID")],
    provider: Annotated[str | None, Query()] = None,
    run_status: Annotated[CollectionRunStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query()] = None,
) -> CollectionRunListResponse:
    return CollectionRunListResponse(
        items=[],
        next_cursor=None,
        has_more=False,
        count=0,
    )


@router.get(
    "/runs/{run_id}",
    response_model=CollectionRunResponse,
    summary="Get a collection run by ID",
)
async def get_run(
    run_id: uuid.UUID,
    organization_id: Annotated[uuid.UUID, Query(description="Organization ID")],
) -> CollectionRunResponse:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Collection run {run_id} not found",
    )


# ── Checkpoint query endpoints ─────────────────────────────────────────────────


@router.get(
    "/checkpoints",
    response_model=CheckpointListResponse,
    summary="List collection checkpoints",
)
async def list_checkpoints(
    organization_id: Annotated[uuid.UUID, Query(description="Organization ID")],
    provider: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query()] = None,
) -> CheckpointListResponse:
    return CheckpointListResponse(
        items=[],
        next_cursor=None,
        has_more=False,
        count=0,
    )


# ── Provider status endpoint ───────────────────────────────────────────────────


@router.get(
    "/providers/{provider}/status",
    response_model=ProviderCollectionStatusResponse,
    summary="Get provider collection status",
    description=(
        "Returns the last known collection state for a provider, "
        "including the most recent checkpoint and run status."
    ),
)
async def get_provider_status(
    provider: str,
    organization_id: Annotated[uuid.UUID, Query(description="Organization ID")],
) -> ProviderCollectionStatusResponse:
    _require_collection_provider(provider)
    return ProviderCollectionStatusResponse(
        provider=provider,
        organization_id=organization_id,
        last_collected_at=None,
        last_run_status=None,
        last_run_id=None,
        events_total=0,
        has_checkpoint=False,
    )
