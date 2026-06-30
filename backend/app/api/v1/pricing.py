"""Pricing API endpoints — F-051/F-056 (EP-09).

Endpoints
---------
POST /pricing/calculate       — calculate cost for token counts
GET  /pricing/models          — list model pricing records
GET  /pricing/providers       — list providers with active pricing
POST /pricing/models          — create a new pricing record (admin)

Authentication
--------------
Endpoints require a valid JWT (CurrentUser). Org membership verification
is deferred to EP-10 — for now we validate the JWT and trust the
organization_id query/body parameter.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import DbDep
from app.auth.dependencies import CurrentUser
from app.db.mixins import uuid7
from app.models.model_pricing import ModelPricing
from app.pricing.engine import PricingEngine, PricingNotFoundError
from app.pricing.validator import PricingValidationError, PricingValidator
from app.repositories.model_pricing_repository import ModelPricingRepository
from app.schemas.pricing import (
    ModelPricingCreate,
    ModelPricingListResponse,
    ModelPricingResponse,
    PriceCalculationRequest,
    PriceCalculationResponse,
)

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/pricing", tags=["pricing"])


# ── Price calculation ──────────────────────────────────────────────────────────


@router.post(
    "/calculate",
    response_model=PriceCalculationResponse,
    summary="Calculate cost for token counts",
    description=(
        "Resolves the applicable pricing version for the given provider/model "
        "and calculates deterministic cost using Decimal arithmetic. "
        "Returns HTTP 404 if no pricing configuration exists."
    ),
)
async def calculate_price(
    body: PriceCalculationRequest,
    db: DbDep,
    _user: CurrentUser,
    # NOTE: org membership verification is deferred to EP-10.
    # In EP-09 we validate the JWT (CurrentUser) only.
) -> PriceCalculationResponse:
    """Calculate cost from token counts."""
    pricing_repo = ModelPricingRepository(db)
    engine = PricingEngine(pricing_repo)

    usage_date = body.usage_date or datetime.now(tz=UTC).date()

    try:
        pricing = await engine.get_pricing_for_event(body.provider, body.model, usage_date)
        result = engine.calculate_cost(
            pricing,
            prompt_tokens=body.prompt_tokens,
            completion_tokens=body.completion_tokens,
            cached_tokens=body.cached_tokens,
        )
    except PricingNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    total_tokens = body.prompt_tokens + body.completion_tokens + (body.cached_tokens or 0)

    return PriceCalculationResponse(
        provider=body.provider,
        model=body.model,
        currency=result["currency"],
        prompt_tokens=body.prompt_tokens,
        completion_tokens=body.completion_tokens,
        cached_tokens=body.cached_tokens,
        total_tokens=total_tokens,
        prompt_cost=str(result["prompt_cost"]),
        completion_cost=str(result["completion_cost"]),
        cached_cost=str(result["cached_cost"]) if result["cached_cost"] is not None else None,
        total_cost=str(result["total_cost"]),
        model_pricing_id=result["model_pricing_id"],
        calculation_version=result["calculation_version"],
        pricing_date=usage_date,
    )


# ── Model pricing list ─────────────────────────────────────────────────────────


@router.get(
    "/models",
    response_model=ModelPricingListResponse,
    summary="List model pricing records",
    description="Returns pricing records, optionally filtered by provider, model, or is_active.",
)
async def list_model_pricing(
    db: DbDep,
    _user: CurrentUser,
    # NOTE: org membership verification is deferred to EP-10.
    organization_id: Annotated[uuid.UUID, Query(description="Organization ID (required)")],
    provider: Annotated[str | None, Query()] = None,
    model: Annotated[str | None, Query()] = None,
    is_active: Annotated[bool | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ModelPricingListResponse:
    """List model pricing records with optional filters."""
    pricing_repo = ModelPricingRepository(db)

    if provider and model:
        items = await pricing_repo.list_for_model(provider, model)
    elif provider:
        items = await pricing_repo.list_for_provider(provider)
    else:
        # List all active pricing
        page = await pricing_repo.list_page(limit=limit)
        items = page.items

    # Apply is_active filter
    if is_active is not None:
        items = [p for p in items if p.is_active == is_active]

    responses = [ModelPricingResponse.from_orm_model(p) for p in items[:limit]]
    return ModelPricingListResponse(
        items=responses,
        total=len(responses),
        has_more=len(items) > limit,
        next_cursor=None,
    )


# ── Providers list ────────────────────────────────────────────────────────────


@router.get(
    "/providers",
    response_model=list[str],
    summary="List providers with active pricing",
    description=(
        "Returns distinct provider names that have at least one active pricing record. "
        "Provider pricing is platform-wide in EP-09 — this endpoint returns all providers "
        "regardless of organization. Per-organization pricing scope is deferred to EP-10."
    ),
)
async def list_pricing_providers(
    db: DbDep,
    _user: CurrentUser,
    # NOTE: org membership verification and per-org pricing scope deferred to EP-10.
    # The organization_id parameter was removed (it was accepted but silently ignored).
) -> list[str]:
    """Return distinct provider names with active pricing."""
    from sqlalchemy import distinct, select
    from app.models.model_pricing import ModelPricing as MP

    stmt = (
        select(distinct(MP.provider))
        .where(
            MP.deleted_at.is_(None),
            MP.is_active.is_(True),
        )
        .order_by(MP.provider)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ── Admin: create pricing record ──────────────────────────────────────────────


@router.post(
    "/models",
    response_model=ModelPricingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new pricing record (admin)",
    description=(
        "Creates a versioned pricing configuration for a provider/model pair. "
        "Validates the record and checks for date range overlaps before persisting. "
        "Requires BILLING_WRITE permission (JWT authentication required). "
        "Note: full RBAC enforcement deferred to EP-10."
    ),
)
async def create_model_pricing(
    body: ModelPricingCreate,
    db: DbDep,
    _user: CurrentUser,
    # NOTE: full BILLING_WRITE RBAC enforcement is deferred to EP-10.
    # In EP-09 we validate the JWT (CurrentUser) only.
) -> ModelPricingResponse:
    """Create a new pricing record."""
    pricing_repo = ModelPricingRepository(db)
    validator = PricingValidator()

    now = datetime.now(UTC)

    # Build the ORM model
    pricing = ModelPricing()
    pricing.id = uuid7()
    pricing.created_at = now
    pricing.updated_at = now
    pricing.provider = body.provider
    pricing.model = body.model
    pricing.version = body.version
    pricing.currency = body.currency
    pricing.effective_from = body.effective_from
    pricing.effective_to = body.effective_to
    pricing.prompt_token_price = body.prompt_token_price
    pricing.completion_token_price = body.completion_token_price
    pricing.cached_token_price = body.cached_token_price
    pricing.audio_token_price = body.audio_token_price
    pricing.image_price = body.image_price
    pricing.embedding_price = body.embedding_price
    pricing.is_active = body.is_active
    pricing.notes = body.notes

    # Validate fields
    try:
        validator.validate_new_pricing(pricing)
    except PricingValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    # Check for overlapping date ranges
    try:
        await validator.validate_no_overlap(pricing_repo, pricing)
    except PricingValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    # Check for duplicate version
    existing = await pricing_repo.get_by_version(body.provider, body.model, body.version)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Pricing version '{body.version}' already exists for "
                f"{body.provider}/{body.model}"
            ),
        )

    # Persist
    created = await pricing_repo.create(pricing)
    log.info(
        "pricing_created",
        pricing_id=str(created.id),
        provider=created.provider,
        model=created.model,
        version=created.version,
    )

    return ModelPricingResponse.from_orm_model(created)
