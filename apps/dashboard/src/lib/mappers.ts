// DTO mappers: backend API response shapes → frontend component types.
//
// Gaps (backend fields that don't exist yet) are filled with safe zero/empty
// values so pages continue to render without crashing. Each gap is labelled.

import type {
  BackendOverviewResponse,
  BackendTimeSeriesResponse,
  BackendProviderBreakdownResponse,
  BackendModelBreakdownResponse,
  BackendProjectBreakdownResponse,
  BackendOrganizationDashboardResponse,
  BackendKPIResponse,
  BackendHeatmapResponse,
  BackendActivityResponse,
} from "../types/backend";
import type {
  OverviewKPIs,
  TimeSeriesResponse,
  ProvidersResponse,
  ModelsResponse,
  ProjectsResponse,
  OrganizationResponse,
  KPIsResponse,
  HeatmapResponse,
  ActivityFeed,
  Currency,
  Granularity,
} from "../types/api";
import { modelDisplayName } from "../utils";

// ── Overview ──────────────────────────────────────────────────────────────────

export function mapOverview(b: BackendOverviewResponse): OverviewKPIs {
  return {
    total_cost: b.total_spend,                  // name mismatch
    today_cost: b.today_spend,                   // EP-24.1: now surfaced (was previously unused by any card)
    month_cost: b.month_spend,                   // EP-24.1: now surfaced
    total_requests: b.total_requests,
    active_models: b.active_models,
    active_providers: b.active_providers,
    active_projects: b.active_projects,          // EP-24.1: real, was unavailable
    total_input_tokens: b.total_tokens,          // gap: backend has no in/out split at the org-overview level; display total as "in"
    total_output_tokens: 0,                      // gap: unavailable from /dashboard/overview (org-level in/out split doesn't exist; see mapTimeSeries/mapProviders/mapModels for the real per-dimension split)
    avg_cost_per_request: b.avg_cost_per_request, // EP-24.1: real, was "0"
    cost_trend_pct: b.cost_trend_pct !== null ? parseFloat(b.cost_trend_pct) : null, // EP-24.1: real, was 0
    request_trend_pct: b.request_trend_pct !== null ? parseFloat(b.request_trend_pct) : null, // EP-24.1
    token_trend_pct: b.token_trend_pct !== null ? parseFloat(b.token_trend_pct) : null, // EP-24.1
    currency: (b.currency ?? "USD") as Currency,
    period_start: "",                            // gap: not returned by /dashboard/overview
    period_end: "",                              // gap: not returned by /dashboard/overview
  };
}

// ── Time Series ───────────────────────────────────────────────────────────────

export function mapTimeSeries(b: BackendTimeSeriesResponse): TimeSeriesResponse {
  return {
    data: b.points.map((p) => ({
      date: p.date,
      total_cost: p.cost,               // name mismatch
      total_requests: p.requests,       // name mismatch
      total_tokens: p.tokens,           // name mismatch
      input_tokens: p.prompt_tokens,    // EP-24.1: real, powers the Token Trend chart
      output_tokens: p.completion_tokens, // EP-24.1: real
      provider_breakdown: {},           // gap: backend returns no per-provider breakdown per time point
    })),
    granularity: b.granularity as Granularity,
    currency: ((b.points[0]?.currency) ?? "USD") as Currency,
  };
}

// ── Providers ─────────────────────────────────────────────────────────────────

export function mapProviders(b: BackendProviderBreakdownResponse): ProvidersResponse {
  const grandTotal = parseFloat(b.total_cost) || 1; // avoid div-by-zero
  return {
    providers: b.providers.map((p) => ({
      provider: p.provider,
      total_cost: p.total_cost,
      request_count: p.total_requests,            // name mismatch
      model_count: p.model_count,                 // EP-24.1: real, was 0
      input_tokens: p.input_tokens,                // EP-24.1: real, was 0
      output_tokens: p.output_tokens,              // EP-24.1: real, was total-as-proxy
      cost_share_pct:
        (parseFloat(p.total_cost) / grandTotal) * 100, // computed client-side
    })),
    currency: ((b.providers[0]?.currency) ?? "USD") as Currency,
  };
}

// ── Models ────────────────────────────────────────────────────────────────────

export function mapModels(b: BackendModelBreakdownResponse): ModelsResponse {
  return {
    models: b.models.map((m) => {
      const costPerToken =
        m.total_tokens > 0
          ? ((parseFloat(m.total_cost) / m.total_tokens) * 1000).toFixed(6)
          : "0";
      return {
        model_id: m.model,                        // name mismatch: backend uses 'model'
        provider: m.provider,
        display_name: modelDisplayName(m.model),  // gap: computed client-side; not in backend response
        total_cost: m.total_cost,
        request_count: m.total_requests,          // name mismatch
        input_tokens: m.input_tokens,             // EP-24.1: real, was 0
        output_tokens: m.output_tokens,           // EP-24.1: real, was total-as-proxy
        avg_cost_per_request: m.avg_cost_per_request,
        cost_per_1k_tokens: costPerToken,         // gap: computed client-side
      };
    }),
    currency: ((b.models[0]?.currency) ?? "USD") as Currency,
  };
}

// ── Projects ──────────────────────────────────────────────────────────────────
// project_name and budget are now real (EP-24.1). team/top_models/trend
// remain unavailable — no team concept and no per-project trend query exist yet.

export function mapProjects(b: BackendProjectBreakdownResponse): ProjectsResponse {
  return {
    projects: b.projects.map((p) => ({
      project_id: p.project_id ?? "unattributed",
      project_name: p.project_name,                    // EP-24.1: real, was project_id
      team: "",                                          // gap: no team concept in backend
      total_cost: p.total_cost,
      budget: p.budget,                                 // EP-24.1: real, was "0"
      budget_utilization_pct: p.budget_utilization_pct !== null
        ? parseFloat(p.budget_utilization_pct)
        : null,                                          // EP-24.1: real, was 0
      request_count: p.total_requests,                 // name mismatch
      top_models: [],                                  // gap: unavailable
      cost_trend: 0,                                   // gap: unavailable
      trend_data: [],                                  // gap: unavailable
    })),
    currency: ((b.projects[0]?.currency) ?? "USD") as Currency,
  };
}

// ── Organization ──────────────────────────────────────────────────────────────
// Backend returns provider/model/project breakdown; frontend expects departments.
// Provider breakdown rows are mapped to department rows as a structural substitute.
// Fields with no backend equivalent are zeroed.

export function mapOrganization(b: BackendOrganizationDashboardResponse): OrganizationResponse {
  const departments = b.provider_breakdown.map((p) => ({
    department_id: p.provider,
    department_name: p.provider.charAt(0).toUpperCase() + p.provider.slice(1),
    total_cost: p.total_cost,
    budget: "0",                      // gap: no budget in backend
    budget_utilization_pct: 0,        // gap: no budget in backend
    team_count: 0,                    // gap: unavailable
    project_count: 0,                 // gap: unavailable
    request_count: p.total_requests,
  }));

  const grandTotal = parseFloat(b.overview.total_spend);

  return {
    departments,
    total_cost: String(grandTotal),
    total_budget: "0",                // gap: no budget concept in backend
    currency: (b.currency ?? "USD") as Currency,
  };
}

// ── KPIs ──────────────────────────────────────────────────────────────────────
// Backend returns named fields; frontend component expects a generic KPIItem array.

export function mapKPIs(b: BackendKPIResponse): KPIsResponse {
  return {
    kpis: [
      {
        key: "highest_cost_provider",
        label: "Highest Cost Provider",
        value: b.highest_cost_provider ?? "—",
        unit: "",
        trend_pct: 0,
        trend_direction: "flat" as const,
      },
      {
        key: "highest_cost_model",
        label: "Highest Cost Model",
        value: b.highest_cost_model ?? "—",
        unit: "",
        trend_pct: 0,
        trend_direction: "flat" as const,
      },
      {
        key: "avg_cost_per_request",
        label: "Avg Cost / Request",
        value: b.avg_cost_per_request ?? "0",
        unit: b.currency,
        trend_pct: 0,
        trend_direction: "flat" as const,
      },
      {
        key: "avg_cost_per_token",
        label: "Avg Cost / Token",
        value: b.avg_cost_per_token ?? "0",
        unit: b.currency,
        trend_pct: 0,
        trend_direction: "flat" as const,
      },
    ],
    currency: (b.currency ?? "USD") as Currency,
    as_of: b.period_end,
  };
}

// ── Usage Heatmap (EP-24.1) ──────────────────────────────────────────────────

export function mapHeatmap(b: BackendHeatmapResponse): HeatmapResponse {
  return {
    cells: b.cells.map((c) => ({
      hour_of_day: c.hour_of_day,
      day_of_week: c.day_of_week,
      total_cost: c.total_cost,
      total_tokens: c.total_tokens,
      total_requests: c.total_requests,
    })),
    currency: (b.currency ?? "USD") as Currency,
  };
}

// ── Recent Activity (EP-24.1) ────────────────────────────────────────────────

export function mapActivity(b: BackendActivityResponse): ActivityFeed {
  const mapRun = (r: BackendActivityResponse["imports"][number]) => ({
    id: r.id,
    provider: r.provider,
    status: r.status,
    triggeredBy: r.triggered_by,
    startedAt: r.started_at,
    completedAt: r.completed_at,
    eventsCollected: r.events_collected,
    errorMessage: r.error_message,
  });
  return {
    imports: b.imports.map(mapRun),
    syncs: b.syncs.map(mapRun),
    failures: b.failures.map((f) => ({
      connectionId: f.connection_id,
      providerType: f.provider_type,
      displayName: f.display_name,
      lastError: f.last_error,
      lastFailureAt: f.last_failure_at,
      consecutiveFailureCount: f.consecutive_failure_count,
    })),
  };
}
