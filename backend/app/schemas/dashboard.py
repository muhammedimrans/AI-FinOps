"""Dashboard API request/response schemas — EP-10 (F-060 through F-066)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ── F-060 — Executive overview ─────────────────────────────────────────────────


class OverviewResponse(BaseModel):
    """Executive dashboard summary for an organization."""

    model_config = ConfigDict(from_attributes=True)

    total_spend: str          # Decimal serialized as string
    today_spend: str          # Decimal as string
    month_spend: str          # Decimal as string
    total_tokens: int
    total_requests: int
    active_providers: int
    active_models: int
    collection_status: str | None
    last_collection_at: datetime | None
    currency: str


# ── F-061 — Time series ────────────────────────────────────────────────────────


class TimeSeriesPoint(BaseModel):
    """A single time-bucket in a cost time series."""

    model_config = ConfigDict(from_attributes=True)

    date: str                 # ISO date string or ISO week ("2026-W26") or "YYYY-MM"
    cost: str                 # Decimal as string
    tokens: int
    requests: int
    currency: str


class TimeSeriesResponse(BaseModel):
    """Paginated time-series cost data for an organization."""

    model_config = ConfigDict(from_attributes=True)

    granularity: str
    start_date: str
    end_date: str
    points: list[TimeSeriesPoint] = Field(default_factory=list)
    total_cost: str           # Decimal as string — sum of all points
    total_tokens: int
    total_requests: int


# ── F-062 — Provider analytics ─────────────────────────────────────────────────


class ProviderMetrics(BaseModel):
    """Cost and usage metrics for a single AI provider."""

    model_config = ConfigDict(from_attributes=True)

    provider: str
    total_cost: str           # Decimal as string
    total_tokens: int
    total_requests: int
    avg_cost_per_request: str  # Decimal as string
    currency: str


class ProviderBreakdownResponse(BaseModel):
    """Provider-level cost breakdown for a date range."""

    model_config = ConfigDict(from_attributes=True)

    providers: list[ProviderMetrics] = Field(default_factory=list)
    total_cost: str           # Decimal as string — sum across all providers
    period_start: str
    period_end: str


# ── F-063 — Model analytics ────────────────────────────────────────────────────


class ModelMetrics(BaseModel):
    """Cost and usage metrics for a single model."""

    model_config = ConfigDict(from_attributes=True)

    provider: str
    model: str
    total_cost: str           # Decimal as string
    total_tokens: int
    total_requests: int
    avg_cost_per_request: str  # Decimal as string
    currency: str


class ModelBreakdownResponse(BaseModel):
    """Model-level cost breakdown for a date range."""

    model_config = ConfigDict(from_attributes=True)

    models: list[ModelMetrics] = Field(default_factory=list)
    total_cost: str           # Decimal as string — sum across listed models
    period_start: str
    period_end: str


# ── F-065 — Project analytics ──────────────────────────────────────────────────


class ProjectMetrics(BaseModel):
    """Cost and usage metrics for a single project."""

    model_config = ConfigDict(from_attributes=True)

    project_id: str | None    # UUID as string, or None for unattributed
    total_cost: str           # Decimal as string
    total_tokens: int
    total_requests: int
    currency: str


class ProjectBreakdownResponse(BaseModel):
    """Project-level cost breakdown for a date range."""

    model_config = ConfigDict(from_attributes=True)

    projects: list[ProjectMetrics] = Field(default_factory=list)
    total_cost: str           # Decimal as string — sum across all projects
    period_start: str
    period_end: str


# ── F-066 — KPIs ──────────────────────────────────────────────────────────────


class KPIResponse(BaseModel):
    """Derived key performance indicators for a date range."""

    model_config = ConfigDict(from_attributes=True)

    highest_cost_provider: str | None
    highest_cost_model: str | None
    avg_cost_per_request: str | None   # Decimal as string
    avg_cost_per_token: str | None     # Decimal as string
    period_start: str
    period_end: str
    currency: str
