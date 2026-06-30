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
} from "../types/backend";
import type {
  OverviewKPIs,
  TimeSeriesResponse,
  ProvidersResponse,
  ModelsResponse,
  ProjectsResponse,
  OrganizationResponse,
  KPIsResponse,
  Currency,
  Granularity,
} from "../types/api";
import { modelDisplayName } from "./utils";

// ── Overview ──────────────────────────────────────────────────────────────────

export function mapOverview(b: BackendOverviewResponse): OverviewKPIs {
  return {
    total_cost: b.total_spend,                  // name mismatch
    total_requests: b.total_requests,
    active_models: b.active_models,
    active_providers: b.active_providers,
    total_input_tokens: b.total_tokens,          // gap: backend has no in/out split; display total as "in"
    total_output_tokens: 0,                      // gap: unavailable from /dashboard/overview
    avg_cost_per_request: "0",                   // gap: unavailable from /dashboard/overview; comes from /dashboard/kpis
    cost_trend_pct: 0,                           // gap: backend has no trend pct fields
    request_trend_pct: 0,                        // gap: unavailable
    token_trend_pct: 0,                          // gap: unavailable
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
      model_count: 0,                             // gap: unavailable from /dashboard/providers
      input_tokens: 0,                            // gap: backend has no in/out split
      output_tokens: p.total_tokens,              // gap: using total as "output" proxy; not accurate split
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
        input_tokens: 0,                          // gap: backend has no in/out split
        output_tokens: m.total_tokens,            // gap: using total as proxy
        avg_cost_per_request: m.avg_cost_per_request,
        cost_per_1k_tokens: costPerToken,         // gap: computed client-side
      };
    }),
    currency: ((b.models[0]?.currency) ?? "USD") as Currency,
  };
}

// ── Projects ──────────────────────────────────────────────────────────────────
// Many fields are unavailable; they are zeroed and noted.
// The project_id is used as the display name since no project_name exists.

export function mapProjects(b: BackendProjectBreakdownResponse): ProjectsResponse {
  return {
    projects: b.projects.map((p) => ({
      project_id: p.project_id ?? "unattributed",
      project_name: p.project_id ?? "Unattributed",  // gap: no project_name in backend
      team: "",                                        // gap: no team concept in backend
      total_cost: p.total_cost,
      budget: "0",                                     // gap: no budget in backend
      budget_utilization_pct: 0,                       // gap: no budget in backend
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
