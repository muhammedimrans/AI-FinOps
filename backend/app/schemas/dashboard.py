"""Dashboard API request/response schemas — EP-10 (F-060 through F-066)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# ── F-060 — Executive overview ─────────────────────────────────────────────────


class OverviewResponse(BaseModel):
    """Executive dashboard summary for an organization."""

    model_config = ConfigDict(from_attributes=True)

    total_spend: str  # Decimal serialized as string
    today_spend: str  # Decimal as string
    month_spend: str  # Decimal as string
    total_tokens: int
    total_requests: int
    active_providers: int
    active_models: int
    active_projects: int  # EP-24.1
    avg_cost_per_request: str  # Decimal as string (EP-24.1)
    cost_trend_pct: str | None  # Decimal as string (EP-24.1) — 30d vs. prior 30d
    request_trend_pct: str | None  # EP-24.1
    token_trend_pct: str | None  # EP-24.1
    collection_status: str | None
    last_collection_at: datetime | None
    currency: str


# ── F-061 — Time series ────────────────────────────────────────────────────────


class TimeSeriesPoint(BaseModel):
    """A single time-bucket in a cost time series."""

    model_config = ConfigDict(from_attributes=True)

    date: str  # ISO date string or ISO week ("2026-W26") or "YYYY-MM"
    cost: str  # Decimal as string
    tokens: int
    prompt_tokens: int  # EP-24.1 — Token Trend chart's "input tokens"
    completion_tokens: int  # EP-24.1 — Token Trend chart's "output tokens"
    requests: int
    currency: str


class TimeSeriesResponse(BaseModel):
    """Paginated time-series cost data for an organization."""

    model_config = ConfigDict(from_attributes=True)

    granularity: str
    start_date: str
    end_date: str
    points: list[TimeSeriesPoint] = Field(default_factory=list)
    total_cost: str  # Decimal as string — sum of all points
    total_tokens: int
    total_requests: int


# ── F-062 — Provider analytics ─────────────────────────────────────────────────


class ProviderMetrics(BaseModel):
    """Cost and usage metrics for a single AI provider."""

    model_config = ConfigDict(from_attributes=True)

    provider: str
    total_cost: str  # Decimal as string
    total_tokens: int
    input_tokens: int  # EP-24.1
    output_tokens: int  # EP-24.1
    model_count: int  # EP-24.1 — distinct models seen for this provider
    total_requests: int
    avg_cost_per_request: str  # Decimal as string
    currency: str


class ProviderBreakdownResponse(BaseModel):
    """Provider-level cost breakdown for a date range."""

    model_config = ConfigDict(from_attributes=True)

    providers: list[ProviderMetrics] = Field(default_factory=list)
    total_cost: str  # Decimal as string — sum across all providers
    period_start: str
    period_end: str


# ── F-063 — Model analytics ────────────────────────────────────────────────────


class ModelMetrics(BaseModel):
    """Cost and usage metrics for a single model."""

    model_config = ConfigDict(from_attributes=True)

    provider: str
    model: str
    total_cost: str  # Decimal as string
    total_tokens: int
    input_tokens: int  # EP-24.1
    output_tokens: int  # EP-24.1
    total_requests: int
    avg_cost_per_request: str  # Decimal as string
    currency: str


class ModelBreakdownResponse(BaseModel):
    """Model-level cost breakdown for a date range."""

    model_config = ConfigDict(from_attributes=True)

    models: list[ModelMetrics] = Field(default_factory=list)
    total_cost: str  # Decimal as string — sum across listed models
    period_start: str
    period_end: str


# ── F-065 — Project analytics ──────────────────────────────────────────────────


class ProjectMetrics(BaseModel):
    """Cost and usage metrics for a single project."""

    model_config = ConfigDict(from_attributes=True)

    project_id: str | None  # UUID as string, or None for unattributed
    project_name: str  # EP-24.1 — real Project.name, "Unassigned" when project_id is None
    total_cost: str  # Decimal as string
    total_tokens: int
    total_requests: int
    budget: str | None  # EP-24.1 — Decimal as string, Project.budget (None = no budget set)
    budget_utilization_pct: str | None  # EP-24.1 — Decimal as string
    currency: str


class ProjectBreakdownResponse(BaseModel):
    """Project-level cost breakdown for a date range."""

    model_config = ConfigDict(from_attributes=True)

    projects: list[ProjectMetrics] = Field(default_factory=list)
    total_cost: str  # Decimal as string — sum across all projects
    period_start: str
    period_end: str


# ── F-066 — KPIs ──────────────────────────────────────────────────────────────


class KPIResponse(BaseModel):
    """Derived key performance indicators for a date range."""

    model_config = ConfigDict(from_attributes=True)

    highest_cost_provider: str | None
    highest_cost_model: str | None
    avg_cost_per_request: str | None  # Decimal as string
    avg_cost_per_token: str | None  # Decimal as string
    period_start: str
    period_end: str
    currency: str


# ── F-064 — Organization composite ────────────────────────────────────────────


class OrganizationOverviewBlock(BaseModel):
    """Overview block nested inside OrganizationDashboardResponse."""

    model_config = ConfigDict(from_attributes=True)

    total_spend: str
    today_spend: str
    month_spend: str
    total_tokens: int
    total_requests: int
    active_providers: int
    active_models: int
    collection_status: str | None
    last_collection_at: str | None  # ISO datetime string or null


class OrganizationProviderItem(BaseModel):
    """Single provider entry inside OrganizationDashboardResponse."""

    model_config = ConfigDict(from_attributes=True)

    provider: str
    total_cost: str
    total_tokens: int
    total_requests: int
    avg_cost_per_request: str
    currency: str


class OrganizationModelItem(BaseModel):
    """Single model entry inside OrganizationDashboardResponse."""

    model_config = ConfigDict(from_attributes=True)

    provider: str
    model: str
    total_cost: str
    total_tokens: int
    total_requests: int
    avg_cost_per_request: str
    currency: str


class OrganizationProjectItem(BaseModel):
    """Single project entry inside OrganizationDashboardResponse."""

    model_config = ConfigDict(from_attributes=True)

    project_id: str | None
    total_cost: str
    total_tokens: int
    total_requests: int
    currency: str


class OrganizationTrendPoint(BaseModel):
    """Single daily trend point inside OrganizationDashboardResponse."""

    model_config = ConfigDict(from_attributes=True)

    date: str
    cost: str
    tokens: int
    requests: int
    currency: str


class OrganizationDashboardResponse(BaseModel):
    """Composite organization dashboard — F-064.

    Returned by GET /v1/dashboard/organization. Aggregates overview,
    provider breakdown, top models, project breakdown, and 30-day daily
    trend in a single response.
    """

    model_config = ConfigDict(from_attributes=True)

    organization_id: str
    period_start: str
    period_end: str
    currency: str
    overview: OrganizationOverviewBlock
    provider_breakdown: list[OrganizationProviderItem] = Field(default_factory=list)
    top_models: list[OrganizationModelItem] = Field(default_factory=list)
    project_breakdown: list[OrganizationProjectItem] = Field(default_factory=list)
    daily_trend: list[OrganizationTrendPoint] = Field(default_factory=list)


# ── EP-24.1 — Usage heatmap ──────────────────────────────────────────────────


class HeatmapCell(BaseModel):
    """One hour-of-day x day-of-week cell in the usage heatmap."""

    model_config = ConfigDict(from_attributes=True)

    hour_of_day: int  # 0-23 (UTC)
    day_of_week: int  # 0=Sunday .. 6=Saturday (PostgreSQL EXTRACT(dow) convention)
    total_cost: str  # Decimal as string
    total_tokens: int
    total_requests: int
    currency: str


class HeatmapResponse(BaseModel):
    """Cost-weighted hour-of-day x day-of-week grid for a date range."""

    model_config = ConfigDict(from_attributes=True)

    cells: list[HeatmapCell] = Field(default_factory=list)
    period_start: str
    period_end: str
    currency: str


# ── EP-24.1 — Recent activity ────────────────────────────────────────────────


class ActivityRunItem(BaseModel):
    """One usage-collection run (import or scheduled sync)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    provider: str
    status: str
    triggered_by: str
    started_at: datetime
    completed_at: datetime | None
    events_collected: int
    error_message: str | None


class ActivityFailureItem(BaseModel):
    """One provider connection currently in a failed state."""

    model_config = ConfigDict(from_attributes=True)

    connection_id: str
    provider_type: str
    display_name: str
    last_error: str | None
    last_failure_at: datetime | None
    consecutive_failure_count: int


class ActivityResponse(BaseModel):
    """Recent activity feed: latest imports, latest syncs, provider failures."""

    model_config = ConfigDict(from_attributes=True)

    imports: list[ActivityRunItem] = Field(default_factory=list)
    syncs: list[ActivityRunItem] = Field(default_factory=list)
    failures: list[ActivityFailureItem] = Field(default_factory=list)
