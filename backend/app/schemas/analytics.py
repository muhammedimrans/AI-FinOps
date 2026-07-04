"""Analytics API request/response schemas — EP-09."""

from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, Field

# ── Query parameter schemas ────────────────────────────────────────────────────


class AnalyticsQueryParams(BaseModel):
    """Shared query parameters for analytics endpoints."""

    organization_id: uuid.UUID
    start_date: date
    end_date: date


# ── Usage summary ─────────────────────────────────────────────────────────────


class UsageSummaryResponse(BaseModel):
    """Total token usage for an org in a date range."""

    model_config = ConfigDict(from_attributes=True)

    organization_id: str
    start_date: str
    end_date: str
    total_tokens: int
    total_prompt_tokens: int
    total_completion_tokens: int
    total_requests: int
    event_count: int


# ── Cost summary ──────────────────────────────────────────────────────────────


class CostByCurrencyItem(BaseModel):
    """Cost totals for a single currency within an org summary.

    Prevents cross-currency aggregation: USD and EUR totals are always
    returned as separate items, never summed together.
    """

    model_config = ConfigDict(from_attributes=True)

    currency: str
    total_cost: str  # Decimal serialized as str
    total_tokens: int
    record_count: int


class CostSummaryResponse(BaseModel):
    """Total cost for an org in a date range, broken down by currency.

    cost_by_currency contains one entry per currency. In single-currency
    deployments this list has exactly one element. total_cost is the cost
    for the first (or only) currency — provided for backward compatibility
    with single-currency consumers. Multi-currency consumers should read
    cost_by_currency instead.
    """

    model_config = ConfigDict(from_attributes=True)

    organization_id: str
    start_date: str
    end_date: str
    cost_by_currency: list[CostByCurrencyItem] = Field(default_factory=list)
    total_cost: str  # Decimal serialized as str — first currency or "0"
    total_tokens: int
    record_count: int


# ── Breakdown items ───────────────────────────────────────────────────────────


class ProviderBreakdownItem(BaseModel):
    """Cost and token breakdown for a single provider."""

    model_config = ConfigDict(from_attributes=True)

    provider: str
    currency: str
    total_cost: str  # Decimal as str
    total_prompt_cost: str
    total_completion_cost: str
    total_tokens: int
    total_prompt_tokens: int
    total_completion_tokens: int
    record_count: int


class ModelBreakdownItem(BaseModel):
    """Cost and token breakdown for a single model."""

    model_config = ConfigDict(from_attributes=True)

    provider: str
    model: str
    currency: str
    total_cost: str  # Decimal as str
    total_prompt_cost: str
    total_completion_cost: str
    total_tokens: int
    total_prompt_tokens: int
    total_completion_tokens: int
    record_count: int


class ProjectBreakdownItem(BaseModel):
    """Cost and token breakdown for a single project."""

    model_config = ConfigDict(from_attributes=True)

    project_id: str | None  # UUID or None for unattributed
    currency: str
    total_cost: str  # Decimal as str
    total_tokens: int
    record_count: int


class DailyTrendItem(BaseModel):
    """Cost totals for a single day."""

    model_config = ConfigDict(from_attributes=True)

    usage_date: str  # ISO date string
    currency: str
    total_cost: str  # Decimal as str
    total_prompt_cost: str
    total_completion_cost: str
    total_tokens: int
    record_count: int


# ── Org summary ───────────────────────────────────────────────────────────────


class OrgSummaryResponse(BaseModel):
    """Combined usage and cost summary for an organization."""

    model_config = ConfigDict(from_attributes=True)

    organization_id: str
    start_date: str
    end_date: str
    # Usage
    total_tokens: int
    total_prompt_tokens: int
    total_completion_tokens: int
    total_requests: int
    event_count: int
    # Cost — per-currency breakdown
    cost_by_currency: list[CostByCurrencyItem] = Field(default_factory=list)
    total_cost: str  # Decimal as str — first currency or "0"
