"""Pricing API request/response schemas — EP-09."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_serializer


# ── Response schemas ───────────────────────────────────────────────────────────


class ModelPricingResponse(BaseModel):
    """Serialized ModelPricing record for API responses.

    Decimal monetary fields are serialized as strings to avoid JSON float
    precision loss. Consumers should parse these as Decimal on receipt.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    external_id: str
    provider: str
    model: str
    version: str
    currency: str
    effective_from: date
    effective_to: date | None
    prompt_token_price: str
    completion_token_price: str
    cached_token_price: str | None
    audio_token_price: str | None
    image_price: str | None
    embedding_price: str | None
    is_active: bool
    notes: str | None
    created_at: str

    @classmethod
    def from_orm_model(cls, pricing: object) -> ModelPricingResponse:
        """Build response from ORM object, converting Decimal fields to str."""
        return cls(
            id=getattr(pricing, "id"),
            external_id=getattr(pricing, "external_id"),
            provider=getattr(pricing, "provider"),
            model=getattr(pricing, "model"),
            version=getattr(pricing, "version"),
            currency=getattr(pricing, "currency"),
            effective_from=getattr(pricing, "effective_from"),
            effective_to=getattr(pricing, "effective_to"),
            prompt_token_price=str(getattr(pricing, "prompt_token_price")),
            completion_token_price=str(getattr(pricing, "completion_token_price")),
            cached_token_price=(
                str(v) if (v := getattr(pricing, "cached_token_price")) is not None else None
            ),
            audio_token_price=(
                str(v) if (v := getattr(pricing, "audio_token_price")) is not None else None
            ),
            image_price=(
                str(v) if (v := getattr(pricing, "image_price")) is not None else None
            ),
            embedding_price=(
                str(v) if (v := getattr(pricing, "embedding_price")) is not None else None
            ),
            is_active=getattr(pricing, "is_active"),
            notes=getattr(pricing, "notes"),
            created_at=str(getattr(pricing, "created_at")),
        )


class ModelPricingListResponse(BaseModel):
    """Paginated list of ModelPricing records."""

    model_config = ConfigDict(from_attributes=True)

    items: list[ModelPricingResponse]
    total: int
    has_more: bool
    next_cursor: str | None = None


# ── Request schemas ────────────────────────────────────────────────────────────


class ModelPricingCreate(BaseModel):
    """Request body for creating a new pricing record."""

    provider: str = Field(..., min_length=1, max_length=64)
    model: str = Field(..., min_length=1, max_length=255)
    version: str = Field(..., min_length=1, max_length=64)
    currency: str = Field(default="USD", min_length=1, max_length=8)
    effective_from: date
    effective_to: date | None = None
    prompt_token_price: Decimal = Field(..., ge=0, description="Price per 1 prompt token")
    completion_token_price: Decimal = Field(..., ge=0, description="Price per 1 completion token")
    cached_token_price: Decimal | None = Field(default=None, ge=0)
    audio_token_price: Decimal | None = Field(default=None, ge=0)
    image_price: Decimal | None = Field(default=None, ge=0)
    embedding_price: Decimal | None = Field(default=None, ge=0)
    is_active: bool = True
    notes: str | None = None

    @field_validator("effective_to")
    @classmethod
    def _effective_to_after_from(cls, v: date | None, info: object) -> date | None:
        data = getattr(info, "data", {})
        effective_from = data.get("effective_from")
        if v is not None and effective_from is not None and v <= effective_from:
            raise ValueError("effective_to must be after effective_from")
        return v


# ── Price calculation schemas ──────────────────────────────────────────────────


class PriceCalculationRequest(BaseModel):
    """Request body for POST /pricing/calculate."""

    provider: str = Field(..., min_length=1, max_length=64)
    model: str = Field(..., min_length=1, max_length=255)
    prompt_tokens: int = Field(..., ge=0)
    completion_tokens: int = Field(..., ge=0)
    cached_tokens: int | None = Field(default=None, ge=0)
    usage_date: date | None = Field(
        default=None,
        description="Date to resolve pricing for. Defaults to today if omitted.",
    )
    organization_id: uuid.UUID | None = Field(
        default=None,
        description="Organization context for authorization (optional in EP-09).",
    )


class PriceCalculationResponse(BaseModel):
    """Response for POST /pricing/calculate."""

    provider: str
    model: str
    currency: str
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int | None
    total_tokens: int
    # Decimal fields serialized as strings
    prompt_cost: str
    completion_cost: str
    cached_cost: str | None
    total_cost: str
    model_pricing_id: uuid.UUID | None
    calculation_version: str
    pricing_date: date
